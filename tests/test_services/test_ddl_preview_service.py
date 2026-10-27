import networkx as nx
import pytest

from src.models.schemas import LineageEdge
from src.services import ddl_preview_service, graph_service
from src.services.parser_service import SQLParserService


@pytest.fixture(autouse=True)
def fresh_graph():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(1, None)


def add_edge(source, target, source_column="id", target_column="id"):
    graph_service.add_edge(1,
        LineageEdge(
            source_table=source,
            source_column=source_column,
            target_table=target,
            target_column=target_column,
            confidence=1.0,
            source_type="parser",
        )
    )


def test_snapshot_is_detached_from_live_graph():
    add_edge("raw.a", "stg.a")
    copied = graph_service.snapshot(1, )
    copied.remove_node("raw.a")

    assert graph_service.get_all_tables(1, ) == ["raw.a", "stg.a"]


def test_parse_text_events_preserves_ddl_order():
    events, reason = SQLParserService(default_dialect="postgres").parse_text_events(
        "ALTER TABLE a RENAME TO b; DROP TABLE b;", dialect="postgres"
    )

    assert reason is None
    assert [(event.kind, event.order) for event in events] == [("rename", 0), ("drop", 1)]


def test_drop_reports_column_edges_and_orphans_without_mutating_live_graph():
    add_edge("raw.orders", "stg.orders", "id", "order_id")
    add_edge("raw.orders", "stg.orders", "customer_id", "customer_id")
    before_graph = graph_service.snapshot(1, )

    result = ddl_preview_service.preview(1, "DROP TABLE raw.orders;")

    assert {(edge.source_column, edge.target_column) for edge in result.removed_edges} == {
        ("id", "order_id"),
        ("customer_id", "customer_id"),
    }
    assert result.orphaned_tables == ["stg.orders"]
    assert nx.utils.graphs_equal(graph_service.snapshot(1, ), before_graph)


def test_drop_table_is_not_an_orphan_and_unknown_tables_are_not_applied():
    add_edge("raw.orders", "stg.orders")

    dropped = ddl_preview_service.preview(1, "DROP TABLE raw.orders; DROP TABLE missing;")

    assert "raw.orders" not in dropped.orphaned_tables
    assert dropped.statements[1].status == "unknown_table"
    assert dropped.unknown_tables == ["missing"]


def test_drop_risk_covers_only_direct_outgoing_edges_with_column_identity():
    add_edge("upstream", "a", "upstream_id", "id")
    add_edge("a", "downstream", "id", "a_id")
    add_edge("a", "downstream", "code", "a_code")

    result = ddl_preview_service.preview(1, "DROP TABLE a;")

    (group,) = result.risk_by_statement
    assert (group.order, group.table, group.change_kind) == (0, "a", "drop_table")
    assert {(risk.source_column, risk.target_column) for risk in group.risks} == {("id", "a_id"), ("code", "a_code")}
    assert {risk.source_table for risk in group.risks} == {"a"}
    assert all("xóa cả bảng" in risk.risk for risk in group.risks)


def test_unsupported_and_mixed_scripts_are_explicit():
    add_edge("raw.orders", "stg.orders")

    result = ddl_preview_service.preview(1, "DROP TABLE raw.orders; ALTER TABLE stg.orders DROP COLUMN id;")

    assert [statement.status for statement in result.statements] == ["applied", "unsupported"]
    assert len(result.unsupported_statements) == 1
    assert len(result.removed_edges) == 1


def test_invalid_sql_returns_parse_error():
    result = ddl_preview_service.preview(1, "THIS IS NOT VALID SQL (((;")

    assert result.parse_error is not None
    assert result.statements == []
    assert result.removed_edges == []


def test_rename_only_does_not_remove_edges_and_rename_then_drop_does():
    add_edge("raw.a", "stg.a")
    add_edge("stg.a", "mart.a")

    renamed = ddl_preview_service.preview(1, "ALTER TABLE stg.a RENAME TO stg.b;")
    dropped = ddl_preview_service.preview(1, "ALTER TABLE stg.a RENAME TO stg.b; DROP TABLE stg.b;")

    assert renamed.removed_edges == []
    assert renamed.edges_before == renamed.edges_after
    assert {(edge.source_table, edge.target_table) for edge in dropped.removed_edges} == {
        ("raw.a", "stg.a"),
        ("stg.a", "mart.a"),
    }
    assert len(dropped.removed_edges) == dropped.edges_before - dropped.edges_after
    assert [(group.order, group.table, group.change_kind) for group in dropped.risk_by_statement] == [
        (0, "stg.a", "rename_table"),
        (1, "stg.b", "drop_table"),
    ]
    assert {(risk.source_table, risk.target_table) for risk in dropped.risk_by_statement[1].risks} == {
        ("stg.b", "mart.a")
    }


def test_rename_then_drop_reports_the_renamed_orphan():
    add_edge("a", "x")

    result = ddl_preview_service.preview(1, "ALTER TABLE x RENAME TO y; DROP TABLE a;")

    assert result.orphaned_tables == ["y"]


def test_rename_conflict_does_not_merge_or_alias_then_drop():
    add_edge("raw.a", "a")
    add_edge("b", "mart.b")

    conflict = ddl_preview_service.preview(1, "ALTER TABLE a RENAME TO b;")
    after_conflict = ddl_preview_service.preview(1, "ALTER TABLE a RENAME TO b; DROP TABLE a;")

    assert conflict.statements[0].status == "rename_conflict"
    assert conflict.rename_conflicts == [{"table": "a", "new_name": "b"}]
    assert conflict.removed_edges == []
    assert conflict.edges_before == conflict.edges_after
    assert {(edge.source_table, edge.target_table) for edge in after_conflict.removed_edges} == {("raw.a", "a")}


def test_rename_conflict_does_not_mutate_live_graph():
    add_edge("raw.a", "a")
    add_edge("b", "mart.b")
    before_graph = graph_service.snapshot(1, )

    ddl_preview_service.preview(1, "ALTER TABLE a RENAME TO b;")

    assert nx.utils.graphs_equal(graph_service.snapshot(1, ), before_graph)


def test_rename_to_untracked_name_simulates_normally():
    add_edge("raw.a", "a")

    result = ddl_preview_service.preview(1, "ALTER TABLE a RENAME TO untracked_b;")

    assert result.statements[0].status == "applied"
    assert result.rename_conflicts == []
    assert result.removed_edges == []


def test_dialect_override_keeps_statement_order_aligned():
    add_edge("a", "x")

    result = ddl_preview_service.preview(1, "ALTER TABLE x RENAME TO y; DROP TABLE a;", dialect="mysql")

    assert [(statement.kind, statement.order, statement.status) for statement in result.statements] == [
        ("rename", 0, "applied"),
        ("drop", 1, "applied"),
    ]
