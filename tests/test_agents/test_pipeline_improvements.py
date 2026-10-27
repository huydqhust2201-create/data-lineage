"""Tests for Pipeline 1 improvements (issues 3.1-3.6 + dedup).

These tests validate the fixes applied to the ingestion pipeline:
  3.1 - Module-level side effect (parser lazy init)
  3.2 - Duplicate edges when re-ingesting the same folder
  3.4 - LLM extraction sequential (concurrency tested via interface)
  3.6 - No error state / partial failure handling
  + graph_service dedup mechanism
  + DAG validation
"""

from contextlib import contextmanager

import networkx as nx
import pytest

from src.config import get_settings
from src.models.schemas import LineageEdge, LineageEvidence
from src.services import graph_service, llm_extraction_service, review_service, storage_service


@pytest.fixture(autouse=True)
def fresh_graph_and_queue():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(1, None)
    review_service._reset()


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch, database_id):
    # describe_columns_node doc thang Postgres that (khong duoc stub boi cac
    # monkeypatch duoi day) de tim cot chua co mo ta - neu DESCRIPTION_ENABLED=true
    # trong .env, no se co mo ta LUON CA du lieu that dang co trong DB (khong chi
    # 2 bang fixture cua test nay), roi crash vi storage_service.transaction() da
    # bi mock thanh object() o duoi. Ep tat de test khong phu thuoc .env may chay.
    monkeypatch.setattr(get_settings(), "description_enabled", False)
    ids: dict[str, int] = {}
    graph_service._reset_graph(database_id, nx.MultiDiGraph())

    @contextmanager
    def _tx():
        yield object()

    def _ensure(_database_id, name, tx=None):
        return ids.setdefault(name, len(ids) + 1)

    monkeypatch.setattr(storage_service, "transaction", _tx)
    monkeypatch.setattr(storage_service, "advisory_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load", lambda database_id, *_args: graph_service._get_graph(database_id).copy())
    monkeypatch.setattr(storage_service, "save", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "ensure_node", _ensure)
    monkeypatch.setattr(storage_service, "rename_node_by_id", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "mark_dropped", lambda *args, **kwargs: True)
    monkeypatch.setattr(storage_service, "revive_nodes", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        storage_service,
        "upsert_nodes",
        lambda _database_id, records, tx=None: {
            r.current_name: _ensure(_database_id, r.current_name) for r in records
        },
    )
    monkeypatch.setattr(storage_service, "append_node_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "last_event_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *args, **kwargs: [])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *args, **kwargs: {})
    monkeypatch.setattr(storage_service, "replace_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "replace_propagated_column_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "rename_column_schema_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "drop_column_schema_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_service, "sync_breaking_change_alerts", lambda *args, **kwargs: None)
    yield


def _edge(src, tgt, src_col=None, tgt_col=None, **kw):
    return LineageEdge(
        source_table=src,
        source_column=src_col,
        target_table=tgt,
        target_column=tgt_col,
        confidence=kw.get("confidence", 1.0),
        source_type=kw.get("source_type", "parser"),
        transform_type=kw.get("transform_type", "direct"),
        evidence=kw.get("evidence"),
    )


# ======================================================================
#  3.2 - Duplicate edges (graph_service.add_edge dedup)
# ======================================================================


class TestGraphDedup:
    """add_edge must be idempotent: same logical edge twice = 1 edge."""

    def test_exact_duplicate_not_added_twice(self, database_id):
        e = _edge("raw.orders", "stg.orders")
        graph_service.add_edge(database_id, e)
        graph_service.add_edge(database_id, e)
        assert len(graph_service.get_all_edges(database_id, )) == 1

    def test_duplicate_table_level_same_source_type(self, database_id):
        e1 = _edge("raw.orders", "stg.orders")
        e2 = _edge("raw.orders", "stg.orders")
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        assert len(graph_service.get_all_edges(database_id, )) == 1

    def test_duplicate_column_level(self, database_id):
        e1 = _edge("raw.orders", "stg.orders", "id", "order_id")
        e2 = _edge("raw.orders", "stg.orders", "id", "order_id")
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        assert len(graph_service.get_all_edges(database_id, )) == 1

    def test_different_columns_are_separate_edges(self, database_id):
        e1 = _edge("raw.orders", "stg.orders", "id", "order_id")
        e2 = _edge("raw.orders", "stg.orders", "amount", "total")
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        assert len(graph_service.get_all_edges(database_id, )) == 2

    def test_different_source_type_are_separate_edges(self, database_id):
        e1 = _edge("raw.orders", "stg.orders", source_type="parser")
        e2 = _edge("raw.orders", "stg.orders", source_type="llm", confidence=0.9)
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        assert len(graph_service.get_all_edges(database_id, )) == 2

    def test_higher_confidence_updates_existing_edge(self, database_id):
        e1 = _edge("raw.orders", "stg.orders", source_type="llm", confidence=0.7)
        e2 = _edge("raw.orders", "stg.orders", source_type="llm", confidence=0.9)
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        edges = graph_service.get_all_edges(database_id, )
        assert len(edges) == 1
        assert edges[0].confidence == 0.9

    def test_lower_confidence_does_not_downgrade(self, database_id):
        e1 = _edge("raw.orders", "stg.orders", source_type="llm", confidence=0.9)
        e2 = _edge("raw.orders", "stg.orders", source_type="llm", confidence=0.5)
        graph_service.add_edge(database_id, e1)
        graph_service.add_edge(database_id, e2)
        edges = graph_service.get_all_edges(database_id, )
        assert len(edges) == 1
        assert edges[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_re_ingest_same_folder_no_duplicate(self, tmp_path, monkeypatch, database_id):
        """Full pipeline: ingest same folder twice -> edge count stays same."""
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        sql = "SELECT id AS customer_id FROM raw_customers"
        (tmp_path / "model.sql").write_text(sql, encoding="utf-8")

        agent = build_graph()
        await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
        count1 = len(graph_service.get_all_edges(database_id, ))
        assert count1 > 0

        await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
        count2 = len(graph_service.get_all_edges(database_id, ))
        assert count2 == count1


# ======================================================================
#  3.1 - Module-level side effect (parser lazy init)
# ======================================================================


class TestLazyInit:
    """Parser must not be instantiated at module import time."""

    def test_lineage_nodes_has_lazy_parser(self, database_id):
        from src.agents.nodes import lineage_nodes

        assert hasattr(lineage_nodes, "_get_parser")


class TestEvidencePaths:
    @pytest.mark.asyncio
    async def test_parser_evidence_paths_are_relative_on_each_cached_ingest(self, tmp_path, monkeypatch, database_id):
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        sql_file = tmp_path / "models" / "revenue.sql"
        sql_file.parent.mkdir()
        sql_file.write_text("SELECT amount_paid FROM raw_invoices", encoding="utf-8")
        agent = build_graph()

        first = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
        second = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        for result in (first, second):
            assert {edge.evidence.file_path for edge in result["parsed_edges"]} == {"models/revenue.sql"}
            assert {edge.evidence.file_path for event in result["graph_events"] for edge in event.edges} == {
                "models/revenue.sql"
            }
            assert {edge.evidence.file_path for edge in result["confirmed_edges"]} == {"models/revenue.sql"}

    @pytest.mark.asyncio
    async def test_llm_fallback_evidence_paths_are_relative(self, tmp_path, monkeypatch, database_id):
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        sql_file = tmp_path / "models" / "dynamic.sql"
        sql_file.parent.mkdir()
        sql_file.write_text("EXECUTE IMMEDIATE 'select * from raw_invoices'", encoding="utf-8")

        def fake_extract(file_paths, **_kwargs):
            return {
                file_path: [
                    LineageEdge(
                        source_table="raw_invoices",
                        target_table="dynamic",
                        confidence=0.9,
                        source_type="llm",
                        evidence=LineageEvidence(file_path=file_path),
                    )
                ]
                for file_path in file_paths
            }

        monkeypatch.setattr(llm_extraction_service, "extract_edges_from_files", fake_extract)
        result = await build_graph().ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        assert {edge.evidence.file_path for edge in result["llm_edges"]} == {"models/dynamic.sql"}
        assert {edge.evidence.file_path for edge in result["confirmed_edges"]} == {"models/dynamic.sql"}


# ======================================================================
#  3.6 - Error state / partial failure handling
# ======================================================================


class TestErrorReporting:
    """Pipeline should report LLM extraction failures in state."""

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty_edges(self, tmp_path, monkeypatch, database_id):
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        (tmp_path / "dynamic.sql").write_text("EXECUTE IMMEDIATE 'select * from raw.x'", encoding="utf-8")

        def fake_extract_failing(file_paths, dialect=None, **kw):
            return {fp: [] for fp in file_paths}

        monkeypatch.setattr(
            llm_extraction_service,
            "extract_edges_from_files",
            fake_extract_failing,
        )

        agent = build_graph()
        result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        assert result.get("unparsed_files") != []
        assert result.get("llm_edges") == []

    @pytest.mark.asyncio
    async def test_partial_failure_keeps_good_edges(self, tmp_path, monkeypatch, database_id):
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        (tmp_path / "good.sql").write_text("SELECT id AS order_id FROM raw_orders", encoding="utf-8")
        (tmp_path / "bad.sql").write_text("EXECUTE IMMEDIATE 'dynamic stuff'", encoding="utf-8")

        def fake_extract(file_paths, dialect=None, **kw):
            results = {}
            for fp in file_paths:
                if "bad" in fp:
                    results[fp] = []
                else:
                    results[fp] = [
                        LineageEdge(
                            source_table="raw.x",
                            target_table="model_y",
                            confidence=0.9,
                            source_type="llm",
                            transform_type="unknown",
                        )
                    ]
            return results

        monkeypatch.setattr(
            llm_extraction_service,
            "extract_edges_from_files",
            fake_extract,
        )

        agent = build_graph()
        result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        assert len(result.get("parsed_edges", [])) >= 1


# ======================================================================
#  DAG validation after graph_build
# ======================================================================


class TestDAGValidation:
    """graph_build_node should detect cycles after writing edges."""

    @pytest.mark.asyncio
    async def test_cycle_detected_after_build(self, tmp_path, monkeypatch, database_id):
        from src.agents.graph import build_graph

        monkeypatch.setattr(graph_service, "persist", lambda: None)
        # Pre-populate graph with edge a -> model
        graph_service.add_edge(database_id, _edge("model", "downstream_x"))
        (tmp_path / "model.sql").write_text("SELECT col FROM downstream_x", encoding="utf-8")

        agent = build_graph()
        result = await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})
        # After fix: state should have cycle_detected flag
        # (cycle: downstream_x -> model -> downstream_x)
        assert result.get("cycle_detected") is True or graph_service.has_cycle(database_id, )


# ======================================================================
#  S-2 — breaking-change alert sinh từ DDL drop
# ======================================================================


class TestBreakingChangeAlertFromDrop:
    """graph_build_node phải sinh alert khi bảng bị drop mà downstream còn tham chiếu."""

    @pytest.mark.asyncio
    async def test_drop_with_downstream_records_an_alert(self, tmp_path, monkeypatch, database_id):
        """S2-1: seed graph rồi drop -> alert có downstream_tables đúng.

        KHÔNG dùng hai lượt ingest: test hồi quy không được phụ thuộc thứ tự hai
        lần chạy. Seed thẳng graph, rồi cho parser sinh sự kiện drop.
        """
        from src.agents.graph import build_graph

        recorded: list[tuple] = []
        monkeypatch.setattr(graph_service, "persist", lambda: None)
        monkeypatch.setattr(
            storage_service,
            "sync_breaking_change_alerts",
            lambda database_id, detected, tx=None: recorded.append((database_id, detected, tx)),
        )
        graph_service.add_edge(database_id, _edge("upstream_src", "doomed_table"))
        graph_service.add_edge(database_id, _edge("doomed_table", "still_reads_it"))
        (tmp_path / "drop.sql").write_text("DROP TABLE doomed_table;", encoding="utf-8")

        agent = build_graph()
        await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        assert recorded, "drop trên bảng có downstream phải sinh alert"
        _, detected, tx = recorded[0]
        assert tx is not None
        assert len(detected) == 1
        assert detected[0].kind == "drop"
        assert detected[0].table_name == "doomed_table"
        assert "still_reads_it" in detected[0].downstream_tables

    @pytest.mark.asyncio
    async def test_drop_on_an_absent_table_records_nothing(self, tmp_path, monkeypatch, database_id):
        """S2-2: bảng không có trong graph -> 0 alert.

        Gác đúng cơ chế `event.table in working`: drop trên database sạch KHÔNG
        sinh alert, vì bảng chưa tồn tại để mà mất đi.
        """
        from src.agents.graph import build_graph

        recorded: list[tuple] = []
        monkeypatch.setattr(graph_service, "persist", lambda: None)
        monkeypatch.setattr(
            storage_service,
            "sync_breaking_change_alerts",
            lambda database_id, detected, tx=None: recorded.append((database_id, detected, tx)),
        )
        (tmp_path / "drop.sql").write_text("DROP TABLE never_existed;", encoding="utf-8")

        agent = build_graph()
        await agent.ainvoke({"input_path": str(tmp_path), "database_id": database_id})

        assert len(recorded) == 1
        _, detected, tx = recorded[0]
        assert detected == []
        assert tx is not None
