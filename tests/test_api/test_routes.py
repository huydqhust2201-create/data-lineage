from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import psycopg2
import pytest

from src.agents.tools.asset_tools import GetAssetCapability, GetAssetParams
from src.api import routes
from src.config import get_settings
from src.models.schemas import IngestResponse, LineageEdge, OverviewGraph
from src.services import graph_service, review_service, storage_service

_SELECT_SIMPLE_SQL = """
with
source as (
    select * from raw_customers
),
renamed as (
    select id as customer_id from source
)
select * from renamed
"""


def test_breaking_change_schema_restores_acknowledged_and_drops_resolved_at():
    schema = storage_service._BREAKING_CHANGE_ALERTS_SCHEMA
    assert "acknowledged BOOLEAN NOT NULL DEFAULT FALSE" in schema
    assert "DROP COLUMN IF EXISTS resolved_at" in schema
    assert "DELETE FROM breaking_change_alerts" not in schema


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def fresh_graph_and_queue(monkeypatch, database_id):
    graph_service._reset_graph(database_id, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(database_id, None)
    review_service._reset()


@pytest.fixture
def use_real_storage():
    """Opt out of this module's in-memory storage double for an integration test."""
    return None


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch, database_id, request):
    """API tests are graph behavior tests; keep their storage state in memory.

    Ép `description_enabled=False` bất kể `.env` máy chạy test đang bật gì —
    nếu không, khi dev bật DESCRIPTION_ENABLED=true để tay test tính năng mô
    tả cột, các test ingest ở đây sẽ vô tình chạy qua describe_columns_node.
    (Phòng thủ thêm cho `load_live_nodes_for_description`/`load_column_descriptions`
    được stub rỗng bên dưới — 2 lớp bảo vệ cho cùng 1 sự cố từng xảy ra thật.)
    """
    if "use_real_storage" in request.fixturenames:
        yield
        return

    monkeypatch.setattr(get_settings(), "description_enabled", False)
    ids: dict[str, int] = {}
    graph_service._reset_graph(database_id, nx.MultiDiGraph())

    @contextmanager
    def _tx():
        yield object()

    def _ensure(_database_id, name, tx=None):
        return ids.setdefault(name, len(ids) + 1)

    monkeypatch.setattr(storage_service, "transaction", _tx)
    monkeypatch.setattr(storage_service, "advisory_lock", lambda tx, *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load", lambda database_id, *_args: graph_service._get_graph(database_id).copy())
    monkeypatch.setattr(storage_service, "save", lambda _database_id, graph, tx=None: None)
    monkeypatch.setattr(storage_service, "ensure_node", _ensure)
    monkeypatch.setattr(storage_service, "rename_node_by_id", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "mark_dropped", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "revive_nodes", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        storage_service,
        "upsert_nodes",
        lambda _database_id, records, tx=None: {
            record.current_name: _ensure(_database_id, record.current_name) for record in records
        },
    )
    monkeypatch.setattr(storage_service, "append_node_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "last_event_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "clear_nodes", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "clear_breaking_change_alerts", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *args, **kwargs: [])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "load_descriptions_by_names", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "load_column_descriptions_by_names", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "load_column_schema_by_names", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "replace_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "replace_propagated_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "rename_column_schema_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "drop_column_schema_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "record_ingest_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "list_ingest_runs", lambda *args, **kwargs: [])
    monkeypatch.setattr(storage_service, "sync_breaking_change_alerts", lambda *args, **kwargs: None)
    yield


@pytest.mark.asyncio
async def test_health(client, database_id):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_graph_includes_table_and_column_descriptions(client, database_id, monkeypatch):
    edge = LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser")
    monkeypatch.setattr(graph_service, "get_all_edges", lambda _database_id: [edge])
    record = storage_service.DescriptionRecord(1, "Prepared orders.", "llm", "schema_inferred", 0.8, "hash", False)
    column = storage_service.ColumnDescriptionRecord(1, "order_id", "Order identifier.", "llm", "schema_inferred", 0.8, "hash", False)
    monkeypatch.setattr(storage_service, "load_descriptions_by_names", lambda *_args: {"stg.orders": record})
    monkeypatch.setattr(storage_service, "load_column_descriptions_by_names", lambda *_args: {("stg.orders", "order_id"): column})
    response = await client.get("/api/v1/graph", params={"database_id": database_id})
    assert response.status_code == 200
    node = next(node for node in response.json()["nodes"] if node["id"] == "stg.orders")
    assert node["description"] == "Prepared orders."
    assert node["columns"] == [{"column": "order_id", "description": "Order identifier.", "label": "schema_inferred", "source": "llm", "is_stale": False}]


@pytest.mark.asyncio
async def test_graph_node_without_description_returns_null_and_empty_columns(client, database_id, monkeypatch):
    edge = LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser")
    monkeypatch.setattr(graph_service, "get_all_edges", lambda _database_id: [edge])
    response = await client.get("/api/v1/graph", params={"database_id": database_id})
    node = next(node for node in response.json()["nodes"] if node["id"] == "stg.orders")
    assert node["description"] is None
    assert node["columns"] == []


@pytest.mark.asyncio
async def test_agent_status(client, database_id):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ingest_parses_directory(client, tmp_path, database_id):
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    response = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()
    assert data["sql_files_found"] == 1
    assert data["parsed_count"] == 1
    assert data["unparsed_count"] == 0
    assert data["pending_review_count"] == 0


@pytest.mark.asyncio
async def test_ingest_run_recorded_and_listed(client, monkeypatch, tmp_path, database_id):
    recorded = []
    monkeypatch.setattr(
        storage_service,
        "record_ingest_run",
        lambda database_id, input_path, **kwargs: recorded.append((database_id, input_path, kwargs)),
    )
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})

    assert len(recorded) == 1
    assert recorded[0][0] == database_id
    assert recorded[0][1] == str(tmp_path)
    assert recorded[0][2]["sql_files_found"] == 1


@pytest.mark.asyncio
async def test_list_ingest_runs_endpoint_returns_stubbed_history(client, monkeypatch, database_id):
    monkeypatch.setattr(
        storage_service,
        "list_ingest_runs",
        lambda _database_id, *args, **kwargs: [
            storage_service.IngestRunRecord(
                id=1,
                database_id=_database_id,
                input_path="/data/jaffle-shop",
                sql_files_found=13,
                parsed_count=13,
                unparsed_count=0,
                pending_review_count=0,
                triggered_by_user_id=None,
                started_at=datetime.now(UTC),
            )
        ],
    )

    response = await client.get("/api/v1/ingest-runs", params={"database_id": database_id})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["input_path"] == "/data/jaffle-shop"
    assert data[0]["sql_files_found"] == 13


@pytest.mark.asyncio
async def test_list_breaking_change_alerts_endpoint_returns_stubbed_alert(client, monkeypatch, database_id):
    calls = []
    monkeypatch.setattr(
        storage_service,
        "list_breaking_change_alerts",
        lambda _database_id, include_acknowledged=False: calls.append(include_acknowledged) or [
            storage_service.BreakingChangeAlertRecord(
                id=1,
                database_id=_database_id,
                kind="drop",
                table_name="raw.orders",
                new_name=None,
                downstream_tables=["stg_orders"],
                suggested_action="Bảng 'raw.orders' đã bị xoá...",
                detected_at=datetime.now(UTC),
                acknowledged=False,
            )
        ],
    )

    response = await client.get(
        "/api/v1/breaking-change-alerts", params={"database_id": database_id, "include_acknowledged": "true"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["kind"] == "drop"
    assert data[0]["table_name"] == "raw.orders"
    assert data[0]["downstream_tables"] == ["stg_orders"]
    assert data[0]["acknowledged"] is False
    assert calls == [True]


@pytest.mark.asyncio
async def test_acknowledge_breaking_change_alert_endpoint(client, monkeypatch, database_id):
    calls = []
    monkeypatch.setattr(
        storage_service,
        "acknowledge_breaking_change_alert",
        lambda database_id, alert_id: calls.append((database_id, alert_id)) or True,
    )
    response = await client.post(
        "/api/v1/breaking-change-alerts/7/acknowledge", params={"database_id": database_id}
    )
    assert response.status_code == 204
    assert calls == [(database_id, 7)]


@pytest.mark.asyncio
async def test_acknowledge_breaking_change_alert_returns_404_when_alert_is_missing(client, monkeypatch, database_id):
    monkeypatch.setattr(storage_service, "acknowledge_breaking_change_alert", lambda *_args: False)

    response = await client.post(
        "/api/v1/breaking-change-alerts/999/acknowledge", params={"database_id": database_id}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ingest_writes_edges_to_requested_database(client, tmp_path, database_id):
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    response = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})

    assert response.status_code == 200
    graph = (await client.get("/api/v1/graph", params={"database_id": database_id})).json()
    assert graph["edges"]


@pytest.mark.asyncio
async def test_ingest_requires_database_id(client, tmp_path, database_id):
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    response = await client.post("/api/v1/ingest", json={"input_path": str(tmp_path)})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_graph_returns_all_edges_for_requested_database(client, tmp_path, database_id):
    # 2 dự án có tên bảng KHÁC nhau — cùng tên bảng ở 2 dự án sẽ bị graph
    # coi là trùng 1 cạnh (dedupe theo source/target/column, không theo
    # project) và merge lại, đây là giới hạn đã biết của kiểu gắn nhãn nhẹ
    # (không tách đồ thị riêng theo project), không phải điều test này verify.
    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    (proj_a / "a.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")
    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    (proj_b / "b.sql").write_text(_SELECT_SIMPLE_SQL.replace("raw_customers", "raw_vendors"), encoding="utf-8")

    await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(proj_a)})
    await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(proj_b)})

    full = (await client.get("/api/v1/graph", params={"database_id": database_id})).json()
    assert len(full["edges"]) == 2


@pytest.mark.asyncio
async def test_ingest_missing_path_returns_error(client, database_id):
    response = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": "does/not/exist"})
    assert response.status_code == 200
    assert response.json()["sql_files_found"] == 0


@pytest.mark.asyncio
async def test_pending_review_confirm_writes_to_graph(client, database_id):
    edge = LineageEdge(
        source_table="raw.a", target_table="stg.a", transform_type="direct", confidence=0.5, source_type="llm"
    )
    review_service.add_pending(database_id, [edge])

    list_response = await client.get("/api/v1/pending-review", params={"database_id": database_id})
    assert len(list_response.json()) == 1

    confirm_response = await client.post(f"/api/v1/pending-review/{edge.edge_id}/confirm", params={"database_id": database_id})
    assert confirm_response.status_code == 200

    graph_response = await client.get("/api/v1/graph", params={"database_id": database_id})
    tables = {node["id"] for node in graph_response.json()["nodes"]}
    assert {"raw.a", "stg.a"} <= tables

    empty_list = await client.get("/api/v1/pending-review", params={"database_id": database_id})
    assert empty_list.json() == []


@pytest.mark.asyncio
@pytest.mark.skipif(not _postgres_available(), reason="Postgres không sẵn sàng ở DATABASE_URL")
async def test_pending_review_confirm_materializes_minimal_asset_profiles(tenant, engineer_client, use_real_storage):
    database_id = tenant["database"].id
    graph_service._reset_graph(database_id, nx.MultiDiGraph())
    edge = LineageEdge(
        source_table="raw.unmaterialized", target_table="stg.unmaterialized", confidence=0.5, source_type="llm"
    )
    review_service.add_pending(database_id, [edge])

    try:
        response = await engineer_client.post(
            f"/api/v1/pending-review/{edge.edge_id}/confirm", params={"database_id": database_id}
        )

        assert response.status_code == 200
        with storage_service.transaction() as tx:
            with tx.cursor() as cur:
                cur.execute(
                    "SELECT current_name FROM lineage_nodes WHERE database_id = %s AND current_name = ANY(%s)",
                    (database_id, [edge.source_table, edge.target_table]),
                )
                materialized_names = {row[0] for row in cur.fetchall()}
        assert materialized_names == {edge.source_table, edge.target_table}

        result = GetAssetCapability().run(
            GetAssetParams(tables=[edge.source_table, edge.target_table]), database_id
        )
        assert result.extra["skipped"] == []
        profiles = {profile.name: profile for profile in result.extra["assets"]}
        assert set(profiles) == {edge.source_table, edge.target_table}
        for profile in profiles.values():
            assert profile.defined_in is None
            assert profile.columns_produced == []
    finally:
        graph_service._reset_graph(database_id, None)
        review_service._reset()


@pytest.mark.asyncio
async def test_pending_review_confirm_ensures_nodes_in_the_callers_transaction(client, monkeypatch, database_id):
    ensured: list[tuple[int, str, object]] = []
    monkeypatch.setattr(
        storage_service,
        "ensure_node",
        lambda current_database_id, name, tx=None: ensured.append((current_database_id, name, tx)) or len(ensured),
    )
    edge = LineageEdge(
        source_table="raw.unmaterialized", target_table="stg.unmaterialized", confidence=0.5, source_type="llm"
    )
    review_service.add_pending(database_id, [edge])

    response = await client.post(f"/api/v1/pending-review/{edge.edge_id}/confirm", params={"database_id": database_id})

    assert response.status_code == 200
    assert [(current_database_id, name) for current_database_id, name, _tx in ensured] == [
        (database_id, edge.source_table),
        (database_id, edge.target_table),
    ]
    assert ensured[0][2] is not None
    assert ensured[0][2] is ensured[1][2]


@pytest.mark.asyncio
async def test_pending_review_reject_discards_edge(client, database_id):
    edge = LineageEdge(
        source_table="raw.b", target_table="stg.b", transform_type="direct", confidence=0.4, source_type="llm"
    )
    review_service.add_pending(database_id, [edge])

    reject_response = await client.post(f"/api/v1/pending-review/{edge.edge_id}/reject", params={"database_id": database_id})
    assert reject_response.status_code == 204

    assert (await client.get("/api/v1/pending-review", params={"database_id": database_id})).json() == []
    graph_response = await client.get("/api/v1/graph", params={"database_id": database_id})
    assert graph_response.json()["nodes"] == []


@pytest.mark.asyncio
async def test_pending_review_confirm_unknown_id_returns_404(client, database_id):
    response = await client.post("/api/v1/pending-review/does-not-exist/confirm", params={"database_id": database_id})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_confirm_failure_restores_original_pending_edge(client, monkeypatch, database_id):
    edge = LineageEdge(source_table="raw.fail", target_table="stg.fail", confidence=0.5, source_type="llm")
    review_service.add_pending(database_id, [edge])
    monkeypatch.setattr(storage_service, "save", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

    with pytest.raises(RuntimeError, match="db down"):
        await client.post(f"/api/v1/pending-review/{edge.edge_id}/confirm", params={"database_id": database_id})

    pending = (await client.get("/api/v1/pending-review", params={"database_id": database_id})).json()
    assert [item["edge_id"] for item in pending] == [edge.edge_id]
    assert pending[0]["evidence"] is None


@pytest.mark.asyncio
async def test_delete_graph_clears_confirmed_and_pending(client, database_id):
    """DELETE /graph là lối thoát thủ công cho user muốn bắt đầu lại từ đầu —
    ingest bình thường vẫn cộng dồn (không tự xoá), xem graph_service.clear(database_id, )."""
    confirmed = LineageEdge(
        source_table="raw.c", target_table="stg.c", transform_type="direct", confidence=1.0, source_type="parser"
    )
    graph_service.add_edge(database_id, confirmed)
    pending = LineageEdge(
        source_table="raw.d", target_table="stg.d", transform_type="direct", confidence=0.4, source_type="llm"
    )
    review_service.add_pending(database_id, [pending])

    delete_response = await client.delete("/api/v1/graph", params={"database_id": database_id})
    assert delete_response.status_code == 204

    graph_response = await client.get("/api/v1/graph", params={"database_id": database_id})
    assert graph_response.json() == {"nodes": [], "edges": []}
    assert (await client.get("/api/v1/pending-review", params={"database_id": database_id})).json() == []


@pytest.mark.asyncio
async def test_delete_graph_clears_node_metadata_too(client, monkeypatch, database_id):
    cleared = []
    monkeypatch.setattr(storage_service, "clear_nodes", lambda _database_id, tx=None: cleared.append(tx))

    response = await client.delete("/api/v1/graph", params={"database_id": database_id})

    assert response.status_code == 204
    assert len(cleared) == 1


@pytest.mark.asyncio
async def test_delete_graph_clears_breaking_change_alerts_in_its_transaction(client, monkeypatch, database_id):
    cleared = []
    monkeypatch.setattr(
        storage_service,
        "clear_breaking_change_alerts",
        lambda _database_id, tx=None: cleared.append((_database_id, tx)),
    )

    response = await client.delete("/api/v1/graph", params={"database_id": database_id})

    assert response.status_code == 204
    assert len(cleared) == 1
    assert cleared[0][0] == database_id
    assert cleared[0][1] is not None


@pytest.mark.asyncio
async def test_impact_downstream(client, database_id):
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        )
    )

    response = await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})

    assert response.status_code == 200
    data = response.json()
    assert data["direction"] == "downstream"
    assert len(data["confirmed"]) == 1
    assert data["confirmed"][0]["target"]["table"] == "stg.orders"
    assert data["confirmed"][0]["hitl_status"] == "confirmed"
    assert data["inferred_pending"] == []


@pytest.mark.asyncio
async def test_impact_downstream_reports_hops_per_edge(client, database_id):
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        )
    )
    graph_service.add_edge(database_id, LineageEdge(
            source_table="stg.orders",
            target_table="fct.orders",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        )
    )
    review_service.add_pending(database_id,
        [
            LineageEdge(
                source_table="fct.orders",
                target_table="dash.orders",
                transform_type="direct",
                confidence=0.5,
                source_type="llm",
            )
        ]
    )

    response = await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})
    data = response.json()

    hops_by_target = {e["target"]["table"]: e["hops"] for e in data["confirmed"]}
    assert hops_by_target["stg.orders"] == 1
    assert hops_by_target["fct.orders"] == 2
    assert data["inferred_pending"][0]["target"]["table"] == "dash.orders"
    assert data["inferred_pending"][0]["hops"] == 3


@pytest.mark.asyncio
async def test_impact_without_change_kind_has_no_risk_field(client, database_id):
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="join",
            confidence=1.0,
            source_type="parser",
        )
    )

    response = await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})
    data = response.json()

    assert data["confirmed"][0]["risk"] is None


@pytest.mark.asyncio
async def test_impact_change_kind_type_returns_risk_note_per_edge(client, database_id):
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="join",
            confidence=1.0,
            source_type="parser",
        )
    )
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.copy",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        )
    )

    response = await client.get(
        "/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream", "change_kind": "type"}
    )
    data = response.json()

    risk_by_target = {e["target"]["table"]: e["risk"] for e in data["confirmed"]}
    assert "cao" in risk_by_target["stg.orders"]
    assert "join" in risk_by_target["stg.orders"]
    assert risk_by_target["stg.copy"] != risk_by_target["stg.orders"]


@pytest.mark.asyncio
async def test_impact_change_kind_drop_and_rename_return_distinct_risk_notes(client, database_id):
    graph_service.add_edge(
        database_id,
        LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="join",
            confidence=1.0,
            source_type="parser",
        ),
    )

    drop_response = await client.get(
        "/api/v1/impact/raw.orders",
        params={"database_id": database_id, "direction": "downstream", "change_kind": "drop"},
    )
    rename_response = await client.get(
        "/api/v1/impact/raw.orders",
        params={"database_id": database_id, "direction": "downstream", "change_kind": "rename"},
    )

    drop_risk = drop_response.json()["confirmed"][0]["risk"]
    rename_risk = rename_response.json()["confirmed"][0]["risk"]

    assert "nghiêm trọng" in drop_risk
    assert "join" in drop_risk
    assert rename_risk != drop_risk
    assert "join" in rename_risk


@pytest.mark.asyncio
async def test_impact_change_kind_drop_table_does_not_say_column(client, database_id):
    """Bug that: chon 'Xoa toan bo bang' o FE nhung risk text van ghi 'xoa cot'
    vi truoc do change_kind='drop' dung chung cho ca cap cot lan cap bang.
    drop_table/rename_table phai la change_kind rieng, van phong noi ve bang."""
    graph_service.add_edge(
        database_id,
        LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        ),
    )

    drop_table_response = await client.get(
        "/api/v1/impact/raw.orders",
        params={"database_id": database_id, "direction": "downstream", "change_kind": "drop_table"},
    )
    rename_table_response = await client.get(
        "/api/v1/impact/raw.orders",
        params={"database_id": database_id, "direction": "downstream", "change_kind": "rename_table"},
    )

    drop_table_risk = drop_table_response.json()["confirmed"][0]["risk"]
    rename_table_risk = rename_table_response.json()["confirmed"][0]["risk"]

    assert "cả bảng" in drop_table_risk
    assert "xóa cột" not in drop_table_risk
    assert "cả bảng" in rename_table_risk
    assert "đổi tên làm downstream không còn thấy cột cũ" not in rename_table_risk
    assert rename_table_risk != drop_table_risk


@pytest.mark.asyncio
async def test_impact_change_kind_covers_pending_edges_too(client, database_id):
    review_service.add_pending(
        database_id,
        [
            LineageEdge(
                source_table="raw.orders",
                target_table="legacy_ltv",
                transform_type="aggregation",
                confidence=0.6,
                source_type="llm",
            )
        ]
    )

    response = await client.get(
        "/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream", "change_kind": "value"}
    )
    data = response.json()

    assert data["inferred_pending"][0]["risk"] is not None
    assert "trung bình" in data["inferred_pending"][0]["risk"]


@pytest.mark.asyncio
async def test_impact_separates_confirmed_and_inferred_pending(client, database_id):
    """Không bao giờ gộp: cạnh chắc chắn (parser) và cạnh nghi ngờ (LLM chưa
    duyệt) cùng đụng vào raw.orders phải nằm ở 2 mảng riêng biệt."""
    graph_service.add_edge(database_id, LineageEdge(
            source_table="raw.orders",
            target_table="stg.orders",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        )
    )
    pending_edge = LineageEdge(
        source_table="raw.orders",
        target_table="customer_ltv",
        transform_type="unknown",
        confidence=0.55,
        source_type="llm",
    )
    review_service.add_pending(database_id, [pending_edge])

    response = await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})
    data = response.json()

    confirmed_targets = {e["target"]["table"] for e in data["confirmed"]}
    pending_targets = {e["target"]["table"] for e in data["inferred_pending"]}
    assert confirmed_targets == {"stg.orders"}
    assert pending_targets == {"customer_ltv"}
    assert data["inferred_pending"][0]["hitl_status"] == "pending"


@pytest.mark.asyncio
async def test_confirm_moves_edge_from_inferred_pending_to_confirmed(client, database_id):
    """Tiêu chí nghiệm thu: xác nhận HITL xong, lần query impact tiếp theo
    (không re-ingest) phải thấy cạnh chuyển hẳn sang confirmed."""
    edge = LineageEdge(
        source_table="raw.orders",
        target_table="customer_ltv",
        transform_type="unknown",
        confidence=0.6,
        source_type="llm",
    )
    review_service.add_pending(database_id, [edge])

    before = (await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})).json()
    assert len(before["inferred_pending"]) == 1
    assert before["confirmed"] == []

    await client.post(f"/api/v1/pending-review/{edge.edge_id}/confirm", params={"database_id": database_id})

    after = (await client.get("/api/v1/impact/raw.orders", params={"database_id": database_id, "direction": "downstream"})).json()
    assert after["inferred_pending"] == []
    assert len(after["confirmed"]) == 1
    assert after["confirmed"][0]["target"]["table"] == "customer_ltv"


@pytest.mark.asyncio
async def test_ingest_returns_overview_graph(client, tmp_path, database_id):
    """Luồng A: /ingest phải tự trả overview_graph, không cần gọi thêm GET /graph."""
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    response = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})
    overview = response.json()["overview_graph"]

    node_ids = {n["id"] for n in overview["nodes"]}
    assert {"raw_customers", "renamed"} <= node_ids
    assert len(overview["confirmed_edges"]) >= 1
    assert overview["pending_edges"] == []  # parser đọc được thẳng -> không có gì pending


@pytest.mark.asyncio
async def test_overview_graph_confirmed_edge_id_cannot_be_confirmed(client, tmp_path, database_id):
    """Bug thật đã xảy ra: overview_graph.confirmed_edges và pending_edges phải
    tách biệt — lấy edge_id từ confirmed_edges gọi /confirm phải 404, vì nó
    chưa từng vào hàng đợi pending (đã ghi thẳng vào graph rồi)."""
    (tmp_path / "renamed.sql").write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    response = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})
    overview = response.json()["overview_graph"]
    assert len(overview["confirmed_edges"]) >= 1

    confirmed_edge_id = overview["confirmed_edges"][0]["edge_id"]
    confirm_response = await client.post(f"/api/v1/pending-review/{confirmed_edge_id}/confirm", params={"database_id": database_id})
    assert confirm_response.status_code == 404


@pytest.mark.asyncio
async def test_confirmed_edge_evidence_has_file_and_raw_sql(client, tmp_path, database_id):
    """Tiêu chí nghiệm thu: 100% cạnh confirmed có raw_sql + file_path + line_range."""
    file_path = tmp_path / "renamed.sql"
    file_path.write_text(_SELECT_SIMPLE_SQL, encoding="utf-8")

    await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})
    data = (await client.get("/api/v1/impact/raw_customers", params={"database_id": database_id, "direction": "downstream"})).json()

    assert len(data["confirmed"]) >= 1
    for edge in data["confirmed"]:
        assert edge["evidence"]["file_path"]
        assert edge["evidence"]["raw_sql"]
        assert edge["evidence"]["line_range"]


@pytest.mark.asyncio
async def test_inferred_pending_evidence_has_reasoning_and_fallback_reason(client, tmp_path, monkeypatch, database_id):
    """Tiêu chí nghiệm thu: 100% cạnh inferred_pending có reasoning + fallback_reason.
    Ép parser fail bằng dynamic SQL (EXECUTE IMMEDIATE), mock LLM trả confidence thấp."""
    from src.models.schemas import LineageEdge as _LineageEdge
    from src.models.schemas import LineageEvidence
    from src.services import llm_extraction_service

    (tmp_path / "legacy.sql").write_text("EXECUTE IMMEDIATE 'select * from raw.x'", encoding="utf-8")

    def fake_extract_edges_from_files(file_paths, dialect=None, *, fallback_reasons=None):
        path = file_paths[0]
        return {
            path: [
                _LineageEdge(
                    source_table="raw.x",
                    target_table="legacy",
                    transform_type="unknown",
                    confidence=0.5,
                    source_type="llm",
                    evidence=LineageEvidence(
                        file_path=path,
                        raw_sql="EXECUTE IMMEDIATE 'select * from raw.x'",
                        reasoning="Dynamic SQL nối chuỗi, suy luận bảng raw.x từ literal trong EXECUTE IMMEDIATE",
                        fallback_reason=(fallback_reasons or {}).get(path),
                    ),
                )
            ]
        }

    monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", fake_extract_edges_from_files)

    await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": str(tmp_path)})
    data = (await client.get("/api/v1/impact/raw.x", params={"database_id": database_id, "direction": "downstream"})).json()

    assert len(data["inferred_pending"]) == 1
    evidence = data["inferred_pending"][0]["evidence"]
    assert evidence["reasoning"]
    assert evidence["fallback_reason"]


@pytest.mark.asyncio
async def test_ingest_chinook_and_sakila(client, database_id):
    """
    Test liên thông (integration) nạp mẫu dbt Jinja Chinook & Sakila qua API.
    Kiểm chứng preprocessing dbt Jinja hoạt động và đồ thị được cập nhật đầy đủ.
    """
    # Nạp Chinook
    response_chinook = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": "samples/chinook"})
    assert response_chinook.status_code == 200
    data_chinook = response_chinook.json()
    assert data_chinook["sql_files_found"] == 1
    assert data_chinook["parsed_count"] == 6

    # Kiểm tra nodes trong đồ thị Chinook
    overview_chinook = data_chinook["overview_graph"]
    node_ids_chinook = {n["id"] for n in overview_chinook["nodes"]}
    assert "employee" in node_ids_chinook
    assert "customer" in node_ids_chinook
    assert "track" in node_ids_chinook
    assert "invoice_line" in node_ids_chinook
    assert "sales_by_album_agent" in node_ids_chinook

    # Nạp Sakila
    response_sakila = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": "samples/sakila"})
    assert response_sakila.status_code == 200
    data_sakila = response_sakila.json()
    assert data_sakila["sql_files_found"] == 1
    assert data_sakila["parsed_count"] == 8

    # Kiểm tra nodes trong đồ thị Sakila
    overview_sakila = data_sakila["overview_graph"]
    node_ids_sakila = {n["id"] for n in overview_sakila["nodes"]}
    assert "actor" in node_ids_sakila
    assert "customer" in node_ids_sakila
    assert "actor_revenue_by_store" in node_ids_sakila

    # Nạp Alarm
    response_alarm = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": "samples/alarm"})
    assert response_alarm.status_code == 200
    data_alarm = response_alarm.json()
    assert data_alarm["sql_files_found"] == 2
    assert data_alarm["parsed_count"] == 16

    # Kiểm tra nodes trong đồ thị Alarm
    overview_alarm = data_alarm["overview_graph"]
    node_ids_alarm = {n["id"] for n in overview_alarm["nodes"]}
    assert "Alarm" in node_ids_alarm
    assert "User" in node_ids_alarm
    assert "History" in node_ids_alarm
    assert "alarm_quiz_performance" in node_ids_alarm
    assert "alarm_face_mission_memories" in node_ids_alarm

    # Nạp Olist
    response_olist = await client.post("/api/v1/ingest", json={"database_id": database_id, "input_path": "samples/olist"})
    assert response_olist.status_code == 200
    data_olist = response_olist.json()
    assert data_olist["sql_files_found"] == 1
    assert data_olist["parsed_count"] == 8

    # Kiểm tra nodes trong đồ thị Olist
    overview_olist = data_olist["overview_graph"]
    node_ids_olist = {n["id"] for n in overview_olist["nodes"]}
    assert "items" in node_ids_olist
    assert "sellers" in node_ids_olist
    assert "olist_seller_segmentation" in node_ids_olist


@pytest.mark.asyncio
async def test_ingest_upload_parses_single_file(client, database_id):
    files = [("files", ("renamed.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain"))]
    response = await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})

    assert response.status_code == 200
    data = response.json()
    assert data["sql_files_found"] == 1
    assert data["parsed_count"] == 1
    assert len(data["overview_graph"]["confirmed_edges"]) >= 1


@pytest.mark.asyncio
async def test_ingest_upload_uses_named_last_modified_map_and_ignores_invalid_json(client, monkeypatch, database_id):
    captured = []

    async def fake_run(input_path, database_id, user_id):
        sql_file = Path(input_path) / "models" / "good.sql"
        captured.append(sql_file.stat().st_mtime)
        return IngestResponse(
            sql_files_found=1,
            parsed_count=0,
            unparsed_count=0,
            pending_review_count=0,
            overview_graph=OverviewGraph(nodes=[], confirmed_edges=[], pending_edges=[]),
        )

    monkeypatch.setattr(routes.ingest_service, "run_ingest", fake_run)
    files = [
        ("files", ("../../skipped.sql", b"select 1", "text/plain")),
        ("files", ("models/good.sql", b"select 1", "text/plain")),
    ]
    stamp_ms = 1_700_000_000_000
    response = await client.post(
        "/api/v1/ingest/upload",
        files=files,
        data={"database_id": str(database_id), "last_modified": '{"models/good.sql": 1700000000000}'},
    )

    assert response.status_code == 200
    assert captured == [stamp_ms / 1000]

    captured.clear()
    response = await client.post(
        "/api/v1/ingest/upload",
        files=[("files", ("models/good.sql", b"select 1", "text/plain"))],
        data={"database_id": str(database_id), "last_modified": "not-json"},
    )
    assert response.status_code == 200
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_ingest_upload_preserves_relative_path_in_evidence(client, database_id):
    """webkitRelativePath (client gửi làm filename) phải giữ nguyên cấu trúc
    thư mục con -> evidence.file_path còn ý nghĩa, không phẳng hết ra root."""
    files = [("files", ("project/models/staging/renamed.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain"))]
    response = await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})

    impact = await client.get("/api/v1/impact/raw_customers", params={"database_id": database_id, "direction": "downstream"})
    edge = impact.json()["confirmed"][0]
    assert edge["evidence"]["file_path"] == "project/models/staging/renamed.sql"
    response_edge = response.json()["overview_graph"]["confirmed_edges"][0]
    assert not response_edge["evidence"]["file_path"].startswith("/")


@pytest.mark.asyncio
async def test_ingest_upload_keeps_multiple_files_in_requested_database(client, database_id):
    files = [
        ("files", ("jaffle-shop/models/staging/renamed.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain")),
        (
            "files",
            (
                "jaffle-shop/models/marts/copy.sql",
                _SELECT_SIMPLE_SQL.replace("renamed", "copy").encode("utf-8"),
                "text/plain",
            ),
        ),
    ]
    await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})

    graph = (await client.get("/api/v1/graph", params={"database_id": database_id})).json()
    assert len(graph["edges"]) == 2


@pytest.mark.asyncio
async def test_ingest_upload_does_not_expose_project_on_edges(client, database_id):
    files = [("files", ("jaffle-shop/models/renamed.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain"))]
    await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})

    graph = (await client.get("/api/v1/graph", params={"database_id": database_id})).json()
    assert "project" not in graph["edges"][0]


@pytest.mark.asyncio
async def test_ingest_upload_accepts_mixed_folder_layout(client, database_id):
    files = [
        ("files", ("renamed.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain")),
        (
            "files",
            ("other/copy.sql", _SELECT_SIMPLE_SQL.replace("renamed", "copy").encode("utf-8"), "text/plain"),
        ),
    ]
    await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})

    graph = (await client.get("/api/v1/graph", params={"database_id": database_id})).json()
    assert len(graph["edges"]) == 2


@pytest.mark.asyncio
async def test_ingest_upload_rejects_non_sql_files(client, database_id):
    files = [("files", ("readme.txt", b"not sql", "text/plain"))]
    response = await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ingest_upload_ignores_path_traversal_filename(client, database_id):
    """Filename kiểu ../../evil.sql không được thoát khỏi thư mục tạm trên server."""
    files = [("files", ("../../evil.sql", _SELECT_SIMPLE_SQL.encode("utf-8"), "text/plain"))]
    response = await client.post("/api/v1/ingest/upload", files=files, data={"database_id": str(database_id)})
    assert response.status_code == 400
