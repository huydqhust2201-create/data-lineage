import os
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import networkx as nx
import psycopg2
import pytest

from src.config import get_settings
from src.services import storage_service


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


# clean_table (dưới) XÓA SẠCH lineage_edges/lineage_nodes trên chính DATABASE_URL
# đang cấu hình — không có DB test riêng, đây LÀ Postgres dev thật của bất kỳ
# ai chạy `pytest tests/` cục bộ. Việc này từng thật sự xóa mất dữ liệu demo
# đã ingest tay của 1 dev (Postgres port 5435 dùng chung cho cả dev lẫn test).
# Mặc định SKIP để không lặp lại — chỉ chạy khi người chạy tự xác nhận
# DATABASE_URL đang trỏ tới Postgres bỏ đi được (CI, container tạm...).
_DB_WIPE_ALLOWED = os.environ.get("PYTEST_ALLOW_DB_WIPE") == "1"

pytestmark = pytest.mark.skipif(
    not _postgres_available() or not _DB_WIPE_ALLOWED,
    reason="Test này xóa sạch lineage_edges/lineage_nodes trên DATABASE_URL đang cấu hình. "
    "SKIP theo mặc định để tránh vô tình xóa dữ liệu dev/demo thật. Set PYTEST_ALLOW_DB_WIPE=1 "
    "chỉ khi chắc chắn DATABASE_URL đang trỏ tới Postgres test/disposable, không phải Postgres dev.",
)


@pytest.fixture(autouse=True)
def clean_table(database_id):
    """Mỗi test bắt đầu từ các bảng storage rỗng."""
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)
    yield
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)


def test_load_empty_table_returns_empty_multidigraph(database_id):
    graph = storage_service.load(database_id)
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_nodes() == 0


def test_save_then_load_roundtrip(database_id):
    original = nx.MultiDiGraph()
    original.add_edge(
        "raw.orders",
        "stg.orders",
        source_column="id",
        target_column="order_id",
        transform_type="direct",
        confidence=1.0,
        source_type="parser",
    )

    storage_service.save(database_id, original)
    loaded = storage_service.load(database_id)

    assert isinstance(loaded, nx.MultiDiGraph)
    assert loaded.has_edge("raw.orders", "stg.orders")
    edge_data = list(loaded.get_edge_data("raw.orders", "stg.orders").values())[0]
    assert edge_data["source_column"] == "id"
    assert edge_data["target_column"] == "order_id"
    assert edge_data["confidence"] == 1.0


def test_save_preserves_parallel_edges(database_id):
    original = nx.MultiDiGraph()
    original.add_edge(
        "t1", "t2", source_column="a", target_column="a", transform_type="direct", confidence=1.0, source_type="parser"
    )
    original.add_edge(
        "t1", "t2", source_column="b", target_column="b", transform_type="direct", confidence=1.0, source_type="parser"
    )

    storage_service.save(database_id, original)
    loaded = storage_service.load(database_id)

    assert loaded.number_of_edges("t1", "t2") == 2


def test_save_overwrites_previous_snapshot(database_id):
    first = nx.MultiDiGraph()
    first.add_edge("a", "b", transform_type="direct", confidence=1.0, source_type="parser")
    storage_service.save(database_id, first)

    second = nx.MultiDiGraph()
    second.add_edge("x", "y", transform_type="direct", confidence=1.0, source_type="parser")
    storage_service.save(database_id, second)

    loaded = storage_service.load(database_id)
    assert not loaded.has_edge("a", "b")
    assert loaded.has_edge("x", "y")


def _node(
    name: str, *, defined_in: str | None = "models/orders.sql", source_file: str | None = None
) -> storage_service.NodeRecord:
    return storage_service.NodeRecord(
        current_name=name,
        defined_in=defined_in,
        source_file=source_file,
        columns_produced=["order_id"],
        columns_consumed=["raw_id"],
        upstream_tables=["raw.orders"],
        downstream_tables=["mart.orders"],
        source_types=["parser"],
        transform_types=["direct"],
        confidence_min=0.8,
        confidence_max=1.0,
    )


def test_upsert_nodes_updates_metadata_without_changing_id(database_id):
    first = storage_service.upsert_nodes(database_id, [_node("stg.orders")])
    second = storage_service.upsert_nodes(database_id, [_node("stg.orders", defined_in="models/stg_orders.sql")])

    assert first["stg.orders"] == second["stg.orders"]
    loaded = storage_service.load_nodes(database_id, ["stg.orders"])
    assert loaded["stg.orders"].defined_in == "models/stg_orders.sql"


def test_save_edges_does_not_delete_nodes(database_id):
    storage_service.upsert_nodes(database_id, [_node("standalone")])

    storage_service.save(database_id, nx.MultiDiGraph())

    assert "standalone" in storage_service.all_node_names(database_id)


def test_ensure_node_is_idempotent_and_rename_keeps_id(database_id):
    node_id = storage_service.ensure_node(database_id, "raw.orders")

    assert storage_service.ensure_node(database_id, "raw.orders") == node_id
    assert storage_service.rename_node_by_id(database_id, node_id, "stg.orders") is True
    assert storage_service.rename_node_by_id(database_id, node_id, "stg.orders") is False
    assert storage_service.ensure_node(database_id, "stg.orders") == node_id


def test_mark_dropped_keeps_node_and_all_node_names_includes_it(database_id):
    node_id = storage_service.ensure_node(database_id, "old.orders")
    dropped_at = datetime.now(UTC)

    assert storage_service.mark_dropped(database_id, node_id, dropped_at) is True
    assert storage_service.mark_dropped(database_id, node_id, dropped_at + timedelta(seconds=1)) is False
    assert storage_service.all_node_names(database_id) == ["old.orders"]


def test_append_events_and_last_event_time(database_id):
    node_id = storage_service.ensure_node(database_id, "stg.orders")
    first = datetime(2026, 8, 15, tzinfo=UTC)
    second = first + timedelta(hours=1)

    storage_service.append_node_events(database_id,
        [
            storage_service.NodeEvent(node_id=node_id, kind="modified", occurred_at=first),
            storage_service.NodeEvent(
                node_id=node_id, kind="rename", occurred_at=second, details={"from": "a", "to": "b"}
            ),
        ]
    )

    assert storage_service.last_event_time(database_id, node_id) == second


def test_load_nodes_reads_batch_and_omits_unknown_names(database_id):
    storage_service.upsert_nodes(database_id, [_node("a"), _node("b")])

    loaded = storage_service.load_nodes(database_id, ["a", "b", "missing"])

    assert set(loaded) == {"a", "b"}
    assert loaded["a"].columns_produced == ["order_id"]


def test_clear_nodes_removes_nodes_and_events(database_id):
    node_id = storage_service.ensure_node(database_id, "stg.orders")
    storage_service.append_node_events(database_id,
        [storage_service.NodeEvent(node_id=node_id, kind="modified", occurred_at=datetime.now(UTC))]
    )

    storage_service.clear_nodes(database_id)

    assert storage_service.all_node_names(database_id) == []
    assert storage_service.last_event_time(database_id, node_id) is None


def _description(node_id: int, *, evidence_hash: str = "hash") -> storage_service.DescriptionRecord:
    return storage_service.DescriptionRecord(
        node_id=node_id,
        description="Orders prepared for reporting.",
        source="llm",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash=evidence_hash,
        is_stale=False,
    )


def test_description_roundtrip_and_semantic_search_excludes_dropped_nodes(database_id):
    ids = storage_service.upsert_nodes(database_id, [_node("stg.orders"), _node("old.orders")])
    records = [_description(ids["stg.orders"]), _description(ids["old.orders"], evidence_hash="old")]

    assert storage_service.upsert_llm_descriptions(database_id,
        records,
        {record.node_id: [1.0] + [0.0] * 1023 for record in records},
        {record.node_id: None for record in records},
    ) == [ids["stg.orders"], ids["old.orders"]]
    assert storage_service.load_descriptions(database_id, [ids["stg.orders"]])[ids["stg.orders"]].description

    storage_service.mark_dropped(database_id, ids["old.orders"], datetime.now(UTC))
    matches = storage_service.search_descriptions(database_id, [1.0] + [0.0] * 1023, limit=10)

    assert matches[0][0] == "stg.orders"
    assert "old.orders" not in {name for name, _, _ in matches}


def test_human_description_wins_over_ingest_and_confirm_can_replace_it(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    assert storage_service.put_human_description(database_id, node_id, "Human description", "human-hash", None)

    assert (
        storage_service.upsert_llm_descriptions(database_id,
            [_description(node_id, evidence_hash="new")], {}, {node_id: "human-hash"}
        )
        == []
    )
    assert storage_service.confirm_pending_description(database_id,
        _description(node_id, evidence_hash="new"), None, "human", "human-hash"
    )
    loaded = storage_service.load_descriptions(database_id, [node_id])[node_id]
    assert loaded.source == "llm"
    assert loaded.evidence_hash == "new"


def test_clear_nodes_removes_descriptions(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id)], {}, {node_id: None})

    storage_service.clear_nodes(database_id)

    assert storage_service.load_descriptions(database_id, [node_id]) == {}


def test_load_live_nodes_for_description_returns_complete_joined_metadata(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    modified_at = datetime(2026, 8, 18, 1, tzinfo=UTC)
    storage_service.append_node_events(database_id, [storage_service.NodeEvent(node_id, "modified", modified_at)])
    assert storage_service.put_human_description(database_id, node_id, "Human orders", "human-hash", None)

    [loaded] = storage_service.load_live_nodes_for_description(database_id)

    assert loaded.node_id == node_id
    assert loaded.record == _node("stg.orders")
    assert loaded.description == storage_service.DescriptionRecord(
        node_id=node_id,
        description="Human orders",
        source="human",
        label=None,
        confidence=None,
        evidence_hash="human-hash",
        is_stale=False,
    )
    assert loaded.last_modified == modified_at


def test_load_live_nodes_for_description_returns_none_for_new_description(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("new.orders")])["new.orders"]

    [loaded] = storage_service.load_live_nodes_for_description(database_id)

    assert loaded.node_id == node_id
    assert loaded.description is None


def test_load_description_node_includes_dropped_node_and_missing_returns_none(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("old.orders")])["old.orders"]
    storage_service.mark_dropped(database_id, node_id, datetime.now(UTC))

    assert storage_service.load_description_node(database_id, node_id).node_id == node_id  # type: ignore[union-attr]
    assert storage_service.load_description_node(database_id, 999_999) is None


def test_description_lookup_by_name_survives_rename(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id)], {}, {node_id: None})
    assert storage_service.rename_node_by_id(database_id, node_id, "mart.orders")

    assert storage_service.load_description_by_name(database_id, "stg.orders") is None
    found_id, found = storage_service.load_description_by_name(database_id, "mart.orders")  # type: ignore[misc]
    assert found_id == node_id
    assert found.description == "Orders prepared for reporting."


def test_mark_descriptions_stale_only_updates_matching_human_hash(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.put_human_description(database_id, node_id, "Human description", "old-hash", None)

    storage_service.mark_descriptions_stale(database_id, [node_id], {node_id: "old-hash"})
    assert storage_service.load_descriptions(database_id, [node_id])[node_id].is_stale is True

    storage_service.put_human_description(database_id, node_id, "New human description", "new-hash", None)
    storage_service.mark_descriptions_stale(database_id, [node_id], {node_id: "old-hash"})
    assert storage_service.load_descriptions(database_id, [node_id])[node_id].is_stale is False


def test_clear_descriptions_keeps_nodes(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id)], {}, {node_id: None})

    storage_service.clear_descriptions(database_id)

    assert storage_service.load_descriptions(database_id, [node_id]) == {}
    assert storage_service.load_description_node(database_id, node_id) is not None


def test_search_descriptions_ranks_cosine_and_skips_null_embedding(database_id):
    ids = storage_service.upsert_nodes(database_id, [_node("near"), _node("far"), _node("no_vector")])
    records = [_description(ids[name], evidence_hash=name) for name in ids]
    storage_service.upsert_llm_descriptions(database_id,
        records,
        {
            ids["near"]: [1.0] + [0.0] * 1023,
            ids["far"]: [0.0, 1.0] + [0.0] * 1022,
        },
        {node_id: None for node_id in ids.values()},
    )

    matches = storage_service.search_descriptions(database_id, [1.0] + [0.0] * 1023, limit=10)

    assert [name for name, _, _ in matches] == ["near", "far"]
    assert matches[0][2] > matches[1][2]


def test_save_edges_does_not_delete_descriptions(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("standalone")])["standalone"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id)], {}, {node_id: None})

    storage_service.save(database_id, nx.MultiDiGraph())

    assert storage_service.load_descriptions(database_id, [node_id])[node_id].description


def test_llm_insert_requires_expected_snapshot_and_does_not_replace_existing_row(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id, evidence_hash="first")], {}, {node_id: None})

    assert (
        storage_service.upsert_llm_descriptions(database_id, [_description(node_id, evidence_hash="second")], {}, {node_id: None})
        == []
    )
    with pytest.raises(KeyError):
        storage_service.upsert_llm_descriptions(database_id, [_description(node_id)], {}, {})


def test_drop_keeps_description_out_of_search_and_revive_reuses_it(tmp_path, database_id):
    source_file = tmp_path / "orders.sql"
    source_file.write_text("select 1", encoding="utf-8")
    record = _node("stg.orders", source_file=str(source_file))
    node_id = storage_service.upsert_nodes(database_id, [record])["stg.orders"]
    storage_service.put_human_description(database_id, node_id, "Human description", "hash", [1.0] + [0.0] * 1023)
    storage_service.mark_dropped(database_id, node_id, datetime.now(UTC))

    assert storage_service.load_descriptions(database_id, [node_id])[node_id].source == "human"
    assert storage_service.load_live_nodes_for_description(database_id) == []
    assert storage_service.search_descriptions(database_id, [1.0] + [0.0] * 1023, limit=10) == []

    assert storage_service.revive_nodes(database_id, [record])[0][0] == node_id
    assert storage_service.load_live_nodes_for_description(database_id)[0].description.description == "Human description"


def test_confirm_pending_description_rejects_changed_llm_hash(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_descriptions(database_id, [_description(node_id, evidence_hash="current")], {}, {node_id: None})

    assert not storage_service.confirm_pending_description(database_id,
        _description(node_id, evidence_hash="proposal"), None, "llm", "old-snapshot"
    )
    assert storage_service.load_descriptions(database_id, [node_id])[node_id].evidence_hash == "current"


def test_description_hnsw_index_uses_cosine_ops(database_id):
    conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'lineage_node_descriptions_hnsw'"
            )
            (indexdef,) = cur.fetchone()
    finally:
        conn.close()

    assert "USING hnsw (embedding vector_cosine_ops)" in indexdef


def _column_description(
    node_id: int, column_name: str = "order_id", *, evidence_hash: str = "hash"
) -> storage_service.ColumnDescriptionRecord:
    return storage_service.ColumnDescriptionRecord(
        node_id=node_id,
        column_name=column_name,
        description="Order identifier.",
        source="llm",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash=evidence_hash,
        is_stale=False,
    )


def test_column_description_roundtrip_and_semantic_search_excludes_dropped_nodes(database_id):
    ids = storage_service.upsert_nodes(database_id, [_node("stg.orders"), _node("old.orders")])
    records = [_column_description(ids["stg.orders"]), _column_description(ids["old.orders"], evidence_hash="old")]

    assert storage_service.upsert_llm_column_descriptions(database_id,
        records,
        {(record.node_id, record.column_name): [1.0] + [0.0] * 1023 for record in records},
        {(record.node_id, record.column_name): None for record in records},
    ) == [(ids["stg.orders"], "order_id"), (ids["old.orders"], "order_id")]
    assert storage_service.load_column_descriptions(database_id, [ids["stg.orders"]])[(ids["stg.orders"], "order_id")].description

    storage_service.mark_dropped(database_id, ids["old.orders"], datetime.now(UTC))
    matches = storage_service.search_column_descriptions(database_id, [1.0] + [0.0] * 1023, limit=10)

    assert matches[0][0] == "stg.orders"
    assert "old.orders" not in {table for table, _, _, _ in matches}


def test_human_column_description_wins_over_ingest_and_confirm_can_replace_it(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    assert storage_service.put_human_column_description(database_id, node_id, "order_id", "Human description", "human-hash", None)

    assert (
        storage_service.upsert_llm_column_descriptions(database_id,
            [_column_description(node_id, evidence_hash="new")], {}, {(node_id, "order_id"): "human-hash"}
        )
        == []
    )
    assert storage_service.confirm_pending_column_description(database_id,
        _column_description(node_id, evidence_hash="new"), None, "human", "human-hash"
    )
    loaded = storage_service.load_column_descriptions(database_id, [node_id])[(node_id, "order_id")]
    assert loaded.source == "llm"
    assert loaded.evidence_hash == "new"


def test_clear_nodes_removes_column_descriptions(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(database_id, [_column_description(node_id)], {}, {(node_id, "order_id"): None})

    storage_service.clear_nodes(database_id)

    assert storage_service.load_column_descriptions(database_id, [node_id]) == {}


def test_load_column_descriptions_batches_multiple_columns_and_nodes(database_id):
    ids = storage_service.upsert_nodes(database_id, [_node("a"), _node("b")])
    storage_service.upsert_llm_column_descriptions(database_id,
        [
            _column_description(ids["a"], "col1", evidence_hash="a1"),
            _column_description(ids["a"], "col2", evidence_hash="a2"),
            _column_description(ids["b"], "col1", evidence_hash="b1"),
        ],
        {},
        {(ids["a"], "col1"): None, (ids["a"], "col2"): None, (ids["b"], "col1"): None},
    )

    loaded = storage_service.load_column_descriptions(database_id, [ids["a"], ids["b"]])

    assert set(loaded) == {(ids["a"], "col1"), (ids["a"], "col2"), (ids["b"], "col1")}
    assert storage_service.load_column_descriptions(database_id, []) == {}


def test_column_description_lookup_by_name_survives_rename(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(database_id, [_column_description(node_id)], {}, {(node_id, "order_id"): None})
    assert storage_service.rename_node_by_id(database_id, node_id, "mart.orders")

    assert storage_service.load_column_description_by_name(database_id, "stg.orders", "order_id") is None
    found_id, found = storage_service.load_column_description_by_name(database_id, "mart.orders", "order_id")  # type: ignore[misc]
    assert found_id == node_id
    assert found.description == "Order identifier."


def test_mark_column_descriptions_stale_only_updates_matching_human_hash(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.put_human_column_description(database_id, node_id, "order_id", "Human description", "old-hash", None)

    storage_service.mark_column_descriptions_stale(database_id, [(node_id, "order_id")], {(node_id, "order_id"): "old-hash"})
    assert storage_service.load_column_descriptions(database_id, [node_id])[(node_id, "order_id")].is_stale is True

    storage_service.put_human_column_description(database_id, node_id, "order_id", "New human description", "new-hash", None)
    storage_service.mark_column_descriptions_stale(database_id, [(node_id, "order_id")], {(node_id, "order_id"): "old-hash"})
    assert storage_service.load_column_descriptions(database_id, [node_id])[(node_id, "order_id")].is_stale is False


def test_clear_column_descriptions_keeps_nodes(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(database_id, [_column_description(node_id)], {}, {(node_id, "order_id"): None})

    storage_service.clear_column_descriptions(database_id)

    assert storage_service.load_column_descriptions(database_id, [node_id]) == {}
    assert storage_service.load_description_node(database_id, node_id) is not None


def test_search_column_descriptions_ranks_cosine_and_skips_null_embedding(database_id):
    ids = storage_service.upsert_nodes(database_id, [_node("near"), _node("far"), _node("no_vector")])
    records = [_column_description(ids[name], evidence_hash=name) for name in ids]
    storage_service.upsert_llm_column_descriptions(database_id,
        records,
        {
            (ids["near"], "order_id"): [1.0] + [0.0] * 1023,
            (ids["far"], "order_id"): [0.0, 1.0] + [0.0] * 1022,
        },
        {(node_id, "order_id"): None for node_id in ids.values()},
    )

    matches = storage_service.search_column_descriptions(database_id, [1.0] + [0.0] * 1023, limit=10)

    assert [table for table, _, _, _ in matches] == ["near", "far"]
    assert matches[0][3] > matches[1][3]


def test_llm_column_insert_requires_expected_snapshot_and_does_not_replace_existing_row(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(database_id,
        [_column_description(node_id, evidence_hash="first")], {}, {(node_id, "order_id"): None}
    )

    assert (
        storage_service.upsert_llm_column_descriptions(database_id,
            [_column_description(node_id, evidence_hash="second")], {}, {(node_id, "order_id"): None}
        )
        == []
    )
    with pytest.raises(KeyError):
        storage_service.upsert_llm_column_descriptions(database_id, [_column_description(node_id)], {}, {})


def test_confirm_pending_column_description_rejects_changed_llm_hash(database_id):
    node_id = storage_service.upsert_nodes(database_id, [_node("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(database_id,
        [_column_description(node_id, evidence_hash="current")], {}, {(node_id, "order_id"): None}
    )

    assert not storage_service.confirm_pending_column_description(database_id,
        _column_description(node_id, evidence_hash="proposal"), None, "llm", "old-snapshot"
    )
    assert storage_service.load_column_descriptions(database_id, [node_id])[(node_id, "order_id")].evidence_hash == "current"


def test_column_description_hnsw_index_uses_cosine_ops(database_id):
    conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'lineage_column_descriptions_hnsw'"
            )
            (indexdef,) = cur.fetchone()
    finally:
        conn.close()

    assert "USING hnsw (embedding vector_cosine_ops)" in indexdef


def test_transaction_rolls_back_node_metadata_and_edges(database_id):
    graph = nx.MultiDiGraph()
    graph.add_edge("raw.orders", "stg.orders", transform_type="direct", confidence=1.0, source_type="parser")

    with pytest.raises(RuntimeError, match="rollback"):
        with storage_service.transaction() as tx:
            storage_service.upsert_nodes(database_id, [_node("stg.orders")], tx)
            storage_service.save(database_id, graph, tx)
            raise RuntimeError("rollback")

    assert storage_service.load_nodes(database_id, ["stg.orders"]) == {}
    assert storage_service.load(database_id).number_of_edges() == 0


def test_two_postgres_connections_keep_both_serialized_graph_writes(database_id):
    """The advisory lock must serialize writers from separate DB connections."""
    start = Event()
    failures: list[Exception] = []

    def write_edge(source: str, target: str) -> None:
        try:
            start.wait(timeout=2)
            with storage_service.transaction() as tx:
                storage_service.advisory_lock(tx)
                graph = storage_service.load(database_id, tx)
                graph.add_edge(source, target, transform_type="direct", confidence=1.0, source_type="parser")
                storage_service.save(database_id, graph, tx)
        except Exception as exc:  # pragma: no cover - assertion below reports worker failures
            failures.append(exc)

    first = Thread(target=write_edge, args=("raw.a", "stg.a"))
    second = Thread(target=write_edge, args=("raw.b", "stg.b"))
    first.start()
    second.start()
    start.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert failures == []
    graph = storage_service.load(database_id)
    assert graph.has_edge("raw.a", "stg.a")
    assert graph.has_edge("raw.b", "stg.b")


def test_clear_after_inflight_ingest_cannot_resurrect_old_snapshot(database_id):
    """Model ingest × DELETE: DELETE loads only after the in-flight writer commits."""
    ingest_holds_lock = Event()
    allow_ingest_commit = Event()
    failures: list[Exception] = []

    def ingest() -> None:
        try:
            with storage_service.transaction() as tx:
                storage_service.advisory_lock(tx)
                graph = storage_service.load(database_id, tx)
                graph.add_edge("raw.a", "stg.a", transform_type="direct", confidence=1.0, source_type="parser")
                ingest_holds_lock.set()
                assert allow_ingest_commit.wait(timeout=2)
                storage_service.save(database_id, graph, tx)
        except Exception as exc:  # pragma: no cover - assertion below reports worker failures
            failures.append(exc)

    def clear() -> None:
        try:
            assert ingest_holds_lock.wait(timeout=2)
            with storage_service.transaction() as tx:
                storage_service.advisory_lock(tx)
                storage_service.save(database_id, nx.MultiDiGraph(), tx)
        except Exception as exc:  # pragma: no cover - assertion below reports worker failures
            failures.append(exc)

    ingest_thread = Thread(target=ingest)
    clear_thread = Thread(target=clear)
    ingest_thread.start()
    assert ingest_holds_lock.wait(timeout=2)
    clear_thread.start()
    allow_ingest_commit.set()
    ingest_thread.join(timeout=5)
    clear_thread.join(timeout=5)

    assert not ingest_thread.is_alive() and not clear_thread.is_alive()
    assert failures == []
    assert storage_service.load(database_id).number_of_edges() == 0


def test_record_and_list_ingest_runs_orders_newest_first(database_id):
    storage_service.record_ingest_run(
        database_id,
        "/data/first",
        sql_files_found=3,
        parsed_count=2,
        unparsed_count=1,
        pending_review_count=1,
        triggered_by_user_id=None,
    )
    storage_service.record_ingest_run(
        database_id,
        "/data/second",
        sql_files_found=5,
        parsed_count=5,
        unparsed_count=0,
        pending_review_count=0,
        triggered_by_user_id=None,
    )

    # So sánh 2 dòng đầu (mới nhất), không ép bằng toàn bộ list — DB test có
    # thể còn dòng cũ từ lần chạy trước (bảng không bị dọn giữa các test).
    runs = storage_service.list_ingest_runs(database_id)

    assert runs[0].input_path == "/data/second"
    assert runs[0].sql_files_found == 5
    assert runs[1].input_path == "/data/first"
    assert runs[1].pending_review_count == 1
