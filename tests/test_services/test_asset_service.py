import os

import networkx as nx
import psycopg2
import pytest

from src.agents.nodes.lineage_nodes import graph_build_node
from src.config import get_settings
from src.models.schemas import GraphEvent, LineageEdge, LineageEvidence
from src.services import graph_service, storage_service
from src.services.asset_service import build_records_from_graph, relative_to_ingest_root


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


# clean_asset_storage (dưới) xóa sạch lineage_edges/lineage_nodes trên chính
# DATABASE_URL đang cấu hình — xem giải thích đầy đủ ở test_storage_service.py.
# Đã từng thật sự xóa mất dữ liệu demo của 1 dev, mặc định SKIP để không lặp lại.
_DB_WIPE_ALLOWED = os.environ.get("PYTEST_ALLOW_DB_WIPE") == "1"
_DB_WIPE_SKIP_REASON = (
    "Test này xóa sạch lineage_edges/lineage_nodes trên DATABASE_URL đang cấu hình. "
    "SKIP theo mặc định để tránh vô tình xóa dữ liệu dev/demo thật. Set PYTEST_ALLOW_DB_WIPE=1 "
    "chỉ khi chắc chắn DATABASE_URL đang trỏ tới Postgres test/disposable, không phải Postgres dev."
)


@pytest.fixture
def clean_asset_storage(database_id):
    """Use the real projection path; graph-node unit tests keep storage mocked."""
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)
    graph_service._reset_graph(1, nx.MultiDiGraph())
    yield
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)
    graph_service._reset_graph(1, None)


def _event_kinds() -> dict[str, list[str]]:
    conn = psycopg2.connect(get_settings().database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n.current_name, e.kind "
                "FROM lineage_node_events e JOIN lineage_nodes n ON n.id = e.node_id "
                "ORDER BY e.id"
            )
            result: dict[str, list[str]] = {}
            for name, kind in cur.fetchall():
                result.setdefault(name, []).append(kind)
            return result
    finally:
        conn.close()


def _dropped_names() -> set[str]:
    conn = psycopg2.connect(get_settings().database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_name FROM lineage_nodes WHERE dropped_at IS NOT NULL")
            return {name for (name,) in cur.fetchall()}
    finally:
        conn.close()


def _edge(file_path: str, source: str = "a", target: str = "m") -> LineageEdge:
    return LineageEdge(
        source_table=source,
        source_column="id",
        target_table=target,
        target_column="id",
        transform_type="direct",
        confidence=1.0,
        source_type="parser",
        evidence=LineageEvidence(file_path=file_path),
    )


@pytest.mark.skipif(not _postgres_available() or not _DB_WIPE_ALLOWED, reason=_DB_WIPE_SKIP_REASON)
@pytest.mark.parametrize(
    ("case", "expected_names", "dropped", "expected_events"),
    [
        ("D_E", {"a", "m"}, set(), {"a": ["modified"], "m": ["modified"]}),
        ("E_D", {"a", "m"}, set(), {"a": ["modified"], "m": ["modified"]}),
        ("D_X", {"a"}, {"a"}, {"a": ["drop"]}),
        ("D_R", {"b"}, set(), {"b": ["rename"]}),
        ("E_X", {"a", "m"}, {"m"}, {"m": ["drop"]}),
        ("E_R", {"b", "m"}, set(), {"b": ["rename"], "m": ["modified"]}),
        ("X_D", {"a"}, set(), {"a": ["drop", "recreated"]}),
        ("X_E", {"a", "seed"}, set(), {"a": ["drop", "recreated"]}),
        ("R_D", {"a", "b"}, set(), {"b": ["rename"], "a": ["modified"]}),
        ("R_R", {"c"}, set(), {"c": ["rename", "rename"]}),
        ("X_X", {"a"}, {"a"}, {"a": ["drop"]}),
        ("D_D", {"a"}, set(), {"a": ["modified"]}),
    ],
)
def test_graph_event_lifecycle_combinations(
    tmp_path, clean_asset_storage, case, expected_names, dropped, expected_events
, database_id):
    """The r19 5.2e matrix: project ordered D/E/R/X events with real Postgres state."""
    first = tmp_path / "first.sql"
    second = tmp_path / "second.sql"
    first.write_text("-- first", encoding="utf-8")
    second.write_text("-- second", encoding="utf-8")
    os.utime(first, (1_700_000_000, 1_700_000_000))
    os.utime(second, (1_700_000_100, 1_700_000_100))

    edge = _edge(str(first))

    def event(kind, order, table=None, new_name=None, edges=None):
        return GraphEvent(
            file_path=str(first), order=order, kind=kind, table=table, new_name=new_name, edges=edges or []
        )

    scenarios = {
        "D_E": [event("declare", 0, "a"), event("edges", 1, edges=[edge])],
        "E_D": [event("edges", 0, edges=[edge]), event("declare", 1, "a")],
        "D_X": [event("declare", 0, "a"), event("drop", 1, "a")],
        "D_R": [event("declare", 0, "a"), event("rename", 1, "a", "b")],
        "E_X": [event("edges", 0, edges=[edge]), event("drop", 1, "m")],
        "E_R": [event("edges", 0, edges=[edge]), event("rename", 1, "a", "b")],
        "X_D": [event("drop", 0, "a"), event("declare", 1, "a")],
        "X_E": [event("drop", 0, "a"), event("edges", 1, edges=[_edge(str(first), "seed", "a")])],
        "R_D": [event("rename", 0, "a", "b"), event("declare", 1, "a")],
        "R_R": [event("rename", 0, "a", "b"), event("rename", 1, "b", "c")],
        "X_X": [event("drop", 0, "a"), event("drop", 1, "a")],
        "D_D": [event("declare", 0, "a"), GraphEvent(file_path=str(second), order=1, kind="declare", table="a")],
    }

    scenario = scenarios[case]
    confirmed_edges = [edge for item in scenario if item.kind == "edges" for edge in item.edges]
    graph_build_node(
        {"input_path": str(tmp_path), "database_id": database_id, "confirmed_edges": confirmed_edges, "graph_events": scenario}
    )

    assert set(storage_service.all_node_names(database_id)) == expected_names
    assert _dropped_names() == dropped
    assert _event_kinds() == expected_events
    if case in {"D_E", "E_D", "D_R", "D_D"}:
        assert storage_service.load_nodes(database_id, ["a" if case != "D_R" else "b"])[
            "a" if case != "D_R" else "b"
        ].defined_in in {
            "first.sql",
            "second.sql",
        }


@pytest.mark.skipif(not _postgres_available() or not _DB_WIPE_ALLOWED, reason=_DB_WIPE_SKIP_REASON)
def test_reingest_only_records_new_modified_events_when_file_mtime_changes(tmp_path, clean_asset_storage, database_id):
    sql_file = tmp_path / "models.sql"
    sql_file.write_text("-- model", encoding="utf-8")
    os.utime(sql_file, (1_700_000_000, 1_700_000_000))
    edge = _edge(str(sql_file))
    events = [
        GraphEvent(file_path=str(sql_file), order=0, kind="declare", table="a"),
        GraphEvent(file_path=str(sql_file), order=1, kind="edges", edges=[edge]),
    ]
    state = {"input_path": str(tmp_path), "database_id": database_id, "confirmed_edges": [edge], "graph_events": events}

    graph_build_node(state)
    first = _event_kinds()
    graph_build_node(state)
    assert _event_kinds() == first

    os.utime(sql_file, (1_700_000_100, 1_700_000_100))
    graph_build_node(state)
    assert _event_kinds() == {"a": ["modified", "modified"], "m": ["modified", "modified"]}


@pytest.mark.skipif(not _postgres_available() or not _DB_WIPE_ALLOWED, reason=_DB_WIPE_SKIP_REASON)
def test_failed_projection_keeps_database_and_ram_graph_unchanged(tmp_path, clean_asset_storage, monkeypatch, database_id):
    sql_file = tmp_path / "models.sql"
    sql_file.write_text("-- model", encoding="utf-8")
    edge = _edge(str(sql_file))
    event = GraphEvent(file_path=str(sql_file), order=0, kind="edges", edges=[edge])
    monkeypatch.setattr(
        storage_service, "upsert_nodes", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fail"))
    )

    with pytest.raises(RuntimeError, match="fail"):
        graph_build_node(
            {"input_path": str(tmp_path), "database_id": database_id, "confirmed_edges": [edge], "graph_events": [event]}
        )

    assert storage_service.load(database_id).number_of_edges() == 0
    assert graph_service._get_graph(1, ).number_of_edges() == 0


def test_build_records_indexes_edges_and_uses_relative_evidence_path(tmp_path, database_id):
    sql_file = tmp_path / "models" / "orders.sql"
    sql_file.parent.mkdir()
    sql_file.write_text("select 1", encoding="utf-8")
    graph = nx.MultiDiGraph()
    graph.add_edge(
        "raw.orders",
        "mart.orders",
        source_column="id",
        target_column="order_id",
        source_type="parser",
        transform_type="direct",
        confidence=1.0,
        evidence={"file_path": str(sql_file)},
    )

    records = {record.current_name: record for record in build_records_from_graph(graph, {}, str(tmp_path))}

    assert records["mart.orders"].defined_in == "models/orders.sql"
    assert records["mart.orders"].columns_produced == ["order_id"]
    assert records["raw.orders"].columns_consumed == ["id"]
    assert records["mart.orders"].upstream_tables == ["raw.orders"]


def test_build_records_keeps_external_definition_path_absolute(tmp_path, database_id):
    outside_file = tmp_path.parent / f"{tmp_path.name}-orders.sql"
    outside_file.write_text("select 1", encoding="utf-8")

    records = build_records_from_graph(nx.MultiDiGraph(), {"orders": str(outside_file)}, str(tmp_path))

    assert records[0].defined_in == outside_file.resolve().as_posix()
    assert ".." not in records[0].defined_in


def test_relative_to_ingest_root_keeps_external_file_absolute(tmp_path):
    outside_file = tmp_path.parent / f"{tmp_path.name}-outside.sql"
    outside_file.write_text("select 1", encoding="utf-8")

    assert relative_to_ingest_root(str(outside_file), str(tmp_path)) == outside_file.resolve().as_posix()


def test_build_records_includes_standalone_declaration(tmp_path, database_id):
    sql_file = tmp_path / "standalone.sql"
    sql_file.write_text("create table standalone (id int)", encoding="utf-8")

    records = build_records_from_graph(nx.MultiDiGraph(), {"standalone": str(sql_file)}, str(tmp_path))

    assert len(records) == 1
    assert records[0].current_name == "standalone"
    assert records[0].defined_in == "standalone.sql"
