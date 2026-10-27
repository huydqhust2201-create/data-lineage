from contextlib import contextmanager
from types import SimpleNamespace

import networkx as nx
import pytest

from src.agents.graph import agent
from src.config import get_settings
from src.models.schemas import LineageEdge
from src.services import graph_service, llm_extraction_service, review_service, storage_service

_SELECT_SIMPLE_SQL = """
with
source as (
    select * from raw_customers
),
renamed as (
    select
        id as customer_id,
        name as customer_name
    from source
)
select * from renamed
"""


class _AlertSyncCursor:
    def __init__(self):
        self.calls: list[tuple[str, tuple | None]] = []
        self._next_id = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        value = (self._next_id,)
        self._next_id += 1
        return value


class _AlertSyncConnection:
    def __init__(self):
        self.cursor_instance = _AlertSyncCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_sync_breaking_change_alerts_preserves_acknowledgement_when_downstream_is_unchanged(monkeypatch):
    conn = _AlertSyncConnection()
    monkeypatch.setattr(storage_service, "_connect", lambda: conn)
    detected = storage_service.BreakingChangeDetection(
        kind="drop",
        table_name="raw.orders",
        new_name=None,
        downstream_tables=["stg_orders"],
        suggested_action="Update stg_orders.",
    )

    storage_service.sync_breaking_change_alerts(7, [detected])

    upsert, upsert_params = conn.cursor_instance.calls[0]
    assert "ON CONFLICT (database_id, kind, table_name, (COALESCE(new_name, '')))" in upsert
    assert "IS DISTINCT FROM EXCLUDED.downstream_tables THEN FALSE" in upsert
    assert "ELSE breaking_change_alerts.acknowledged END" in upsert
    assert upsert_params[:4] == (7, "drop", "raw.orders", None)
    assert conn.committed is True
    assert conn.closed is True


def test_sync_breaking_change_alerts_does_not_issue_a_resolve_update(monkeypatch):
    conn = _AlertSyncConnection()
    monkeypatch.setattr(storage_service, "_connect", lambda: conn)

    storage_service.sync_breaking_change_alerts(7, [])
    assert conn.cursor_instance.calls == []


@pytest.fixture(autouse=True)
def fresh_graph_and_queue():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(1, None)
    review_service._reset()


@pytest.fixture
def fake_storage(monkeypatch, database_id):
    """Keep pipeline tests in-memory while observing the new save(tx) contract."""
    # describe_columns_node đọc trực tiếp Postgres thật (không được stub bởi các
    # monkeypatch dưới đây) để tìm cột chưa có mô tả — nếu DESCRIPTION_ENABLED=true
    # trong .env, nó sẽ cố mô tả LUÔN CẢ dữ liệu thật đang có trong DB (không chỉ
    # 2 bảng fixture của test này), rồi crash vì storage_service.transaction() đã
    # bị mock thành object() ở dưới. Ép tắt để test không phụ thuộc .env máy chạy.
    monkeypatch.setattr(get_settings(), "description_enabled", False)
    saved = []
    ids: dict[str, int] = {}
    graph_service._reset_graph(database_id, nx.MultiDiGraph())

    @contextmanager
    def _tx():
        yield object()

    def _ensure(_database_id, name, tx=None):
        return ids.setdefault(name, len(ids) + 1)

    def _upsert(_database_id, records, tx=None):
        return {record.current_name: _ensure(_database_id, record.current_name) for record in records}

    monkeypatch.setattr(storage_service, "transaction", _tx)
    monkeypatch.setattr(storage_service, "advisory_lock", lambda tx, *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load", lambda database_id, *_args: graph_service._get_graph(database_id).copy())
    monkeypatch.setattr(storage_service, "save", lambda _database_id, graph, tx=None: saved.append(graph.copy()))
    monkeypatch.setattr(storage_service, "ensure_node", _ensure)
    monkeypatch.setattr(storage_service, "rename_node_by_id", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "mark_dropped", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "revive_nodes", lambda *args, **kwargs: [])
    monkeypatch.setattr(storage_service, "upsert_nodes", _upsert)
    monkeypatch.setattr(storage_service, "append_node_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "last_event_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *args, **kwargs: [])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "replace_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "replace_propagated_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "rename_column_schema_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "drop_column_schema_table", lambda *args, **kwargs: None)

    # breaking_change_alerts trong bộ nhớ — graph_build_node ghi thật (không
    # mock) sẽ crash trên CI nếu Postgres của self-hosted runner không sẵn
    # sàng/không đúng credential. Test pipeline ở đây chỉ quan tâm contract
    # graph -> sync, không cần round-trip Postgres thật.
    alerts: list[dict] = []

    def _sync(_database_id, detected, tx=None):
        for alert in detected:
            key = (alert.kind, alert.table_name, alert.new_name or "")
            existing = next(
                (item for item in alerts if (item["kind"], item["table_name"], item["new_name"] or "") == key),
                None,
            )
            payload = {
                "kind": alert.kind,
                "table_name": alert.table_name,
                "new_name": alert.new_name,
                "downstream_tables": alert.downstream_tables,
                "suggested_action": alert.suggested_action,
                "acknowledged": False,
            }
            if existing is None:
                alerts.append(payload)
            else:
                existing.update(payload)
    def _list_alerts(_database_id, include_acknowledged=False, limit=50, tx=None):
        return [SimpleNamespace(**a) for a in reversed(alerts) if include_acknowledged or not a["acknowledged"]]

    monkeypatch.setattr(storage_service, "sync_breaking_change_alerts", _sync)
    monkeypatch.setattr(storage_service, "list_breaking_change_alerts", _list_alerts)
    return saved


@pytest.mark.asyncio
async def test_pipeline_parses_and_confirms_direct_edges(tmp_path, fake_storage, database_id):
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert len(result["sql_files"]) == 1
    assert len(result["parsed_edges"]) == 2
    assert result["unparsed_files"] == []
    assert result["llm_edges"] == []
    assert len(result["confirmed_edges"]) == 2  # confidence=1.0 >= threshold mặc định 0.8
    assert result["pending_review"] == []
    assert len(fake_storage) == 1
    assert graph_service.get_downstream(database_id, "raw_customers") != []


@pytest.mark.asyncio
async def test_pipeline_empty_directory_produces_no_edges(tmp_path, fake_storage, database_id):

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["sql_files"] == []
    assert result["parsed_edges"] == []
    assert result["confirmed_edges"] == []
    assert fake_storage == []


@pytest.mark.asyncio
async def test_pipeline_syncs_breaking_changes_inside_graph_transaction(tmp_path, fake_storage, database_id, monkeypatch):
    observed_calls = []

    def _sync(_database_id, detected, tx=None):
        observed_calls.append((detected, tx))

    monkeypatch.setattr(storage_service, "sync_breaking_change_alerts", _sync)
    (tmp_path / "model.sql").write_text("CREATE TABLE stg_orders AS SELECT id FROM raw.orders;", encoding="utf-8")

    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert len(observed_calls) == 1
    detected, tx = observed_calls[0]
    assert detected == []
    assert tx is not None


@pytest.mark.asyncio
async def test_pipeline_macro_only_file_skips_llm_fallback(tmp_path, monkeypatch, fake_storage, database_id):
    (tmp_path / "cents_to_dollars.sql").write_text(
        "{% macro cents_to_dollars(column_name) -%}\n"
        "    ({{ column_name }} / 100)::numeric(16, 2)\n"
        "{%- endmacro %}\n",
        encoding="utf-8",
    )

    def fail_if_called(file_paths, dialect=None, *, fallback_reasons=None):
        raise AssertionError("macro-only file should never reach LLM fallback")

    monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", fail_if_called)

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert len(result["sql_files"]) == 1
    assert result["parsed_edges"] == []
    assert result["unparsed_files"] == []
    assert result["confirmed_edges"] == []


@pytest.mark.asyncio
async def test_pipeline_low_confidence_llm_edge_goes_to_pending_review(tmp_path, monkeypatch, fake_storage, database_id):
    # EXECUTE IMMEDIATE khiến parser_service chủ động trả về [] (dynamic SQL).
    (tmp_path / "dynamic.sql").write_text("EXECUTE IMMEDIATE 'select * from raw.x'", encoding="utf-8")

    def fake_extract_edges_from_files(file_paths, dialect=None, *, fallback_reasons=None):
        return {
            file_paths[0]: [
                LineageEdge(
                    source_table="raw.x",
                    target_table="dynamic",
                    transform_type="unknown",
                    confidence=0.5,
                    source_type="llm",
                )
            ]
        }

    monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", fake_extract_edges_from_files)
    # lineage_nodes import trực tiếp llm_extraction_service module nên patch trên module gốc là đủ.

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["unparsed_files"] == [str(tmp_path / "dynamic.sql")]
    assert len(result["llm_edges"]) == 1
    assert result["confirmed_edges"] == []
    assert len(result["pending_review"]) == 1
    assert result["pending_review"][0].confidence == 0.5


@pytest.mark.asyncio
async def test_pipeline_self_loop_does_not_trigger_cycle_alert(tmp_path, monkeypatch, fake_storage, database_id):
    sql_path = tmp_path / "orders.sql"
    sql_path.write_text(
        "CREATE TABLE orders AS SELECT id FROM orders",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        llm_extraction_service,
        "extract_edges_from_files",
        lambda file_paths, dialect=None, *, fallback_reasons=None: {file_paths[0]: []},
    )

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["parsed_edges"] == []
    assert result["cycle_detected"] is False
    assert graph_service.get_all_edges(database_id) == []


@pytest.mark.asyncio
async def test_pipeline_does_not_send_ddl_only_file_to_llm(tmp_path, monkeypatch, fake_storage, database_id):
    (tmp_path / "migration.sql").write_text(
        "ALTER TABLE raw.orders RENAME TO raw.orders_v2",
        encoding="utf-8",
    )

    def llm_must_not_run(*args, **kwargs):
        raise AssertionError("DDL-only file must not go to LLM fallback")

    monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", llm_must_not_run)

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["parsed_edges"] == []
    assert result["unparsed_files"] == []


@pytest.mark.asyncio
async def test_pipeline_applies_ordered_rename_events(tmp_path, fake_storage, database_id):
    (tmp_path / "migration.sql").write_text(
        "CREATE TABLE stg_orders AS SELECT order_id FROM raw.orders; "
        "ALTER TABLE stg_orders RENAME TO stg_orders_v2; "
        "CREATE TABLE mart_sales AS SELECT order_id FROM stg_orders_v2;",
        encoding="utf-8",
    )

    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_downstream(database_id, "raw.orders")} == {
        ("raw.orders", "stg_orders_v2"),
        ("stg_orders_v2", "mart_sales"),
    }


@pytest.mark.asyncio
async def test_pipeline_records_breaking_change_alert_when_dropping_table_with_downstream(
    tmp_path, fake_storage, database_id
):
    (tmp_path / "migration.sql").write_text(
        "CREATE TABLE stg_orders AS SELECT id FROM raw.orders; DROP TABLE raw.orders;",
        encoding="utf-8",
    )

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["breaking_changes_detected"] == 1
    alerts = storage_service.list_breaking_change_alerts(database_id)
    assert len(alerts) == 1
    assert alerts[0].kind == "drop"
    assert alerts[0].table_name == "raw.orders"
    assert alerts[0].downstream_tables == ["stg_orders"]
    assert "stg_orders" in alerts[0].suggested_action


@pytest.mark.asyncio
async def test_pipeline_no_breaking_change_alert_when_dropped_table_has_no_downstream(
    tmp_path, fake_storage, database_id
):
    (tmp_path / "migration.sql").write_text("DROP TABLE lonely_table;", encoding="utf-8")

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert result["breaking_changes_detected"] == 0
    assert storage_service.list_breaking_change_alerts(database_id) == []


@pytest.mark.asyncio
async def test_pipeline_preserves_statement_order_when_reusing_table_name(tmp_path, fake_storage, database_id):
    (tmp_path / "migration.sql").write_text(
        "CREATE TABLE a AS SELECT id FROM s; ALTER TABLE a RENAME TO b; CREATE TABLE a AS SELECT id FROM t;",
        encoding="utf-8",
    )

    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(database_id)} == {
        ("s", "b"),
        ("t", "a"),
    }


@pytest.mark.asyncio
async def test_pipeline_preserves_statement_order_when_recreating_dropped_table(tmp_path, fake_storage, database_id):
    (tmp_path / "migration.sql").write_text(
        "CREATE TABLE a AS SELECT id FROM s; DROP TABLE a; CREATE TABLE a AS SELECT id FROM t;",
        encoding="utf-8",
    )

    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(database_id)} == {("t", "a")}


@pytest.mark.asyncio
async def test_pipeline_keeps_parser_events_when_llm_events_are_pending(tmp_path, monkeypatch, fake_storage, database_id):
    (tmp_path / "model.sql").write_text(
        "CREATE TABLE model AS SELECT id FROM raw.orders",
        encoding="utf-8",
    )
    (tmp_path / "dynamic.sql").write_text(
        "EXECUTE IMMEDIATE 'select * from raw.customers'",
        encoding="utf-8",
    )

    def fake_extract_edges_from_files(file_paths, dialect=None, *, fallback_reasons=None):
        return {
            file_paths[0]: [
                LineageEdge(
                    source_table="raw.customers",
                    target_table="dynamic",
                    confidence=0.5,
                    source_type="llm",
                )
            ]
        }

    monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", fake_extract_edges_from_files)

    result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(database_id)} == {
        ("raw.orders", "model")
    }
    assert [(edge.source_table, edge.target_table) for edge in result["pending_review"]] == [
        ("raw.customers", "dynamic")
    ]


@pytest.mark.asyncio
async def test_pipeline_persists_only_when_ordered_events_change_graph(tmp_path, fake_storage, database_id):
    graph_service.add_edge(database_id, LineageEdge(source_table="s", target_table="a", confidence=1.0, source_type="parser"))
    (tmp_path / "migration.sql").write_text(
        "ALTER TABLE a RENAME TO b",
        encoding="utf-8",
    )

    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
    assert len(fake_storage) == 1
    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(database_id)} == {("s", "b")}

    fake_storage.clear()
    await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
    assert fake_storage == []
