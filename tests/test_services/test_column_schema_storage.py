"""Storage cho lineage_column_schema + round-trip dependency_kind (Chủ đề 3).

Khác test_storage_service.py: KHÔNG bị gate bởi PYTEST_ALLOW_DB_WIPE vì mỗi test
chạy trên 1 database THROWAWAY riêng (tạo + xoá trong fixture), không đụng
database "default" của dev. Chỉ skip khi không có Postgres.
"""

import uuid

import networkx as nx
import psycopg2
import pytest

from src.config import get_settings
from src.services import graph_service, storage_service


def _postgres_available() -> bool:
    try:
        psycopg2.connect(get_settings().database_url, connect_timeout=2).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="cần Postgres")


@pytest.fixture
def db_id():
    """1 database dùng-1-lần, xoá sạch (cascade) sau test."""
    conn = psycopg2.connect(get_settings().database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO databases (owner_id, name) "
                "SELECT id, %s FROM users WHERE email = 'engineer@example.com' RETURNING id",
                (f"test-cs-{uuid.uuid4().hex[:12]}",),
            )
            new_id = cur.fetchone()[0]
        yield new_id
        with conn.cursor() as cur:
            cur.execute("DELETE FROM databases WHERE id = %s", (new_id,))
    finally:
        conn.close()


def _cs(name, **kw):
    return {
        "name": name, "data_type": kw.get("data_type", "INT"),
        "is_nullable": kw.get("is_nullable", True), "is_primary_key": kw.get("is_primary_key", False),
        "is_foreign_key": kw.get("is_foreign_key", False),
        "references_table": kw.get("references_table"), "references_column": kw.get("references_column"),
        "origin": kw.get("origin", "declared"),
    }


# ---- dependency_kind round-trip + dedup lúc load ---------------------------


def test_save_load_roundtrips_dependency_kind(db_id):
    g = nx.MultiDiGraph()
    g.add_edge("stg_x", "mart_y", source_column="k", transform_type="unknown",
               confidence=1.0, source_type="parser", dependency_kind="join_key")
    storage_service.save(db_id, g)
    loaded = storage_service.load(db_id)
    assert list(loaded.get_edge_data("stg_x", "mart_y").values())[0].get("dependency_kind") == "join_key"


def test_load_collapses_exact_duplicate_rows_keeping_highest_confidence(db_id):
    conn = psycopg2.connect(get_settings().database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for conf in (0.7, 0.9, 0.8):
                cur.execute(
                    "INSERT INTO lineage_edges (database_id, source_table, source_column, target_table, "
                    "target_column, transform_type, confidence, source_type, dependency_kind) "
                    "VALUES (%s,'a','id','b','id','direct',%s,'parser','output')",
                    (db_id, conf),
                )
    finally:
        conn.close()
    loaded = storage_service.load(db_id)
    assert loaded.number_of_edges("a", "b") == 1
    assert list(loaded.get_edge_data("a", "b").values())[0]["confidence"] == 0.9


def test_load_keeps_genuinely_distinct_parallel_edges(db_id):
    g = nx.MultiDiGraph()
    g.add_edge("t1", "t2", source_column="a", target_column="a", transform_type="direct",
               confidence=1.0, source_type="parser")
    g.add_edge("t1", "t2", source_column="a", target_column=None, transform_type="unknown",
               confidence=1.0, source_type="parser", dependency_kind="join_key")
    storage_service.save(db_id, g)
    assert storage_service.load(db_id).number_of_edges("t1", "t2") == 2


# ---- lineage_column_schema ----------------------------------------------------


def test_replace_and_load_roundtrip(db_id):
    storage_service.replace_column_schema(db_id, {
        "raw_patients": [
            _cs("patient_id", data_type="INTEGER", is_nullable=False, is_primary_key=True),
            _cs("doctor_id", is_foreign_key=True, references_table="raw_doctors", references_column="doctor_id"),
        ],
    })
    loaded = storage_service.load_column_schema_by_names(db_id, ["raw_patients", "absent"])
    assert list(loaded) == ["raw_patients"]
    assert [c["name"] for c in loaded["raw_patients"]] == ["patient_id", "doctor_id"]  # theo ordinal
    cols = {c["name"]: c for c in loaded["raw_patients"]}
    assert cols["patient_id"]["is_primary_key"] is True and cols["patient_id"]["is_nullable"] is False
    assert cols["doctor_id"]["references_table"] == "raw_doctors"


def test_replace_only_touches_tables_in_mapping(db_id):
    storage_service.replace_column_schema(db_id, {"a": [_cs("x")], "b": [_cs("y")]})
    storage_service.replace_column_schema(db_id, {"b": [_cs("y2")]})
    loaded = storage_service.load_column_schema_by_names(db_id, ["a", "b"])
    assert [c["name"] for c in loaded["a"]] == ["x"]
    assert [c["name"] for c in loaded["b"]] == ["y2"]


def test_empty_mapping_is_noop(db_id):
    storage_service.replace_column_schema(db_id, {"a": [_cs("x")]})
    storage_service.replace_column_schema(db_id, {})
    assert "a" in storage_service.load_column_schema_by_names(db_id, ["a"])


def test_rename_moves_rows(db_id):
    storage_service.replace_column_schema(db_id, {"old_t": [_cs("x", data_type="TEXT")]})
    storage_service.rename_column_schema_table(db_id, "old_t", "new_t")
    loaded = storage_service.load_column_schema_by_names(db_id, ["old_t", "new_t"])
    assert "old_t" not in loaded and loaded["new_t"][0]["data_type"] == "TEXT"


def test_drop_removes_rows(db_id):
    storage_service.replace_column_schema(db_id, {"t": [_cs("x")]})
    storage_service.drop_column_schema_table(db_id, "t")
    assert storage_service.load_column_schema_by_names(db_id, ["t"]) == {}


def test_propagated_never_clobbers_declared(db_id):
    storage_service.replace_column_schema(db_id, {"t": [_cs("x", data_type="INTEGER")]})
    storage_service.replace_propagated_column_schema(db_id, {
        "t": [_cs("x", data_type="TEXT", origin="propagated")],
        "u": [_cs("z", origin="propagated")],
    })
    loaded = storage_service.load_column_schema_by_names(db_id, ["t", "u"])
    assert loaded["t"][0]["data_type"] == "INTEGER" and loaded["t"][0]["origin"] == "declared"
    assert loaded["u"][0]["origin"] == "propagated"
    storage_service.replace_propagated_column_schema(db_id, {})  # xoá hết propagated
    loaded = storage_service.load_column_schema_by_names(db_id, ["t", "u"])
    assert loaded["t"][0]["origin"] == "declared" and "u" not in loaded


def test_ingest_run_rename_drop_wires_column_schema(db_id):
    """graph_build_node: rename/drop bảng -> column_schema đi theo / bị xoá (storage-level)."""
    storage_service.replace_column_schema(db_id, {"raw_old": [_cs("c", data_type="DATE")]})
    storage_service.rename_column_schema_table(db_id, "raw_old", "raw_new")
    storage_service.drop_column_schema_table(db_id, "raw_gone")  # no-op an toàn khi không có
    loaded = storage_service.load_column_schema_by_names(db_id, ["raw_old", "raw_new"])
    assert loaded == {"raw_new": [{
        "name": "c", "data_type": "DATE", "is_nullable": True, "is_primary_key": False,
        "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared",
    }]}


@pytest.mark.asyncio
async def test_full_agent_rename_carries_column_schema_end_to_end(db_id, tmp_path, monkeypatch):
    """END-TO-END: chạy agent thật với DDL nguồn + ALTER RENAME -> column_schema
    của bảng phải đi theo tên mới (verify wiring trong graph_build_node)."""
    from src.agents.graph import build_graph
    from src.config import get_settings as _gs

    monkeypatch.setattr(_gs(), "description_enabled", False)
    graph_service._reset_graph(db_id, nx.MultiDiGraph())
    (tmp_path / "01_src.sql").write_text(
        "CREATE TABLE raw_orders (order_id INTEGER NOT NULL PRIMARY KEY, amount NUMERIC(10,2));",
        encoding="utf-8",
    )
    (tmp_path / "02_migrate.sql").write_text("ALTER TABLE raw_orders RENAME TO raw_orders_v2;", encoding="utf-8")

    await build_graph().ainvoke({"input_path": str(tmp_path), "database_id": db_id})

    loaded = storage_service.load_column_schema_by_names(db_id, ["raw_orders", "raw_orders_v2"])
    assert "raw_orders" not in loaded
    cols = {c["name"]: c for c in loaded["raw_orders_v2"]}
    assert cols["order_id"]["data_type"] == "INT" and cols["order_id"]["is_primary_key"] is True  # sqlglot chuẩn hoá INTEGER->INT
    assert cols["amount"]["data_type"] == "DECIMAL(10, 2)"  # sqlglot chuẩn hoá NUMERIC->DECIMAL
    graph_service._reset_graph(db_id, None)


@pytest.mark.asyncio
async def test_full_agent_drop_removes_column_schema_end_to_end(db_id, tmp_path, monkeypatch):
    """END-TO-END: DROP TABLE -> column_schema của bảng bị xoá."""
    from src.agents.graph import build_graph
    from src.config import get_settings as _gs

    monkeypatch.setattr(_gs(), "description_enabled", False)
    graph_service._reset_graph(db_id, nx.MultiDiGraph())
    (tmp_path / "01_src.sql").write_text(
        "CREATE TABLE raw_tmp (id INTEGER NOT NULL PRIMARY KEY);", encoding="utf-8"
    )
    (tmp_path / "02_drop.sql").write_text("DROP TABLE raw_tmp;", encoding="utf-8")

    await build_graph().ainvoke({"input_path": str(tmp_path), "database_id": db_id})

    assert storage_service.load_column_schema_by_names(db_id, ["raw_tmp"]) == {}
    graph_service._reset_graph(db_id, None)
