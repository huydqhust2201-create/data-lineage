import networkx as nx
import pytest

from src.models.schemas import LineageEdge, LineageEvidence
from src.services import graph_service


@pytest.fixture(autouse=True)
def fresh_graph():
    """Mỗi test chạy trên 1 đồ thị in-memory rỗng, không đụng file thật trên đĩa."""
    graph_service._reset_graph(1, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(1, None)


def _edge(source_table, target_table, source_column=None, target_column=None, **kw) -> LineageEdge:
    return LineageEdge(
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column=target_column,
        confidence=kw.get("confidence", 1.0),
        source_type=kw.get("source_type", "parser"),
        transform_type=kw.get("transform_type", "direct"),
        evidence=kw.get("evidence"),
    )


def test_add_edge_then_get_downstream_table_level():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))

    result = graph_service.get_downstream(1, "raw.orders")

    assert len(result) == 1
    assert result[0].source_table == "raw.orders"
    assert result[0].target_table == "stg.orders"


def test_get_downstream_transitive_multi_hop():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.revenue"))

    result = graph_service.get_downstream(1, "raw.orders")
    tables = {e.target_table for e in result}

    assert tables == {"stg.orders", "mart.revenue"}


def test_get_downstream_with_hops_honors_depth_at_the_public_wrapper():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.revenue"))

    depth_one = graph_service.get_downstream_with_hops(1, "raw.orders", depth=1)
    unlimited = graph_service.get_downstream_with_hops(1, "raw.orders", depth=None)

    assert [(edge.target_table, hops) for edge, hops in depth_one] == [("stg.orders", 1)]
    assert [(edge.target_table, hops) for edge, hops in unlimited] == [
        ("stg.orders", 1),
        ("mart.revenue", 2),
    ]


def test_get_downstream_filters_by_column_on_first_hop():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="order_id"))
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="amount", target_column="amount"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.revenue"))

    result = graph_service.get_downstream(1, "raw.orders", column="id")

    assert len(result) == 2
    first_hop = [e for e in result if e.target_table == "stg.orders"]
    assert len(first_hop) == 1
    assert first_hop[0].source_column == "id"


def test_get_downstream_column_none_edge_always_matches():
    # Cạnh table-level (source_column=None) đại diện "cả bảng" nên vẫn tính
    # là ảnh hưởng dù query hỏi 1 cột cụ thể.
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))

    result = graph_service.get_downstream(1, "raw.orders", column="id")

    assert len(result) == 1


def test_get_upstream_traces_backward():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="order_id"))

    result = graph_service.get_upstream(1, "stg.orders", column="order_id")

    assert len(result) == 1
    assert result[0].source_table == "raw.orders"


def test_get_downstream_column_filter_narrows_across_multiple_hops():
    # 2 chuỗi cột song song từ raw.orders -> stg.orders -> mart.summary: chỉ
    # chuỗi "id" mới được đi tiếp, chuỗi "amount" phải bị loại ở CẢ hop 2 chứ
    # không được rơi về table-level như hành vi cũ.
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="order_id"))
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="amount", target_column="amount"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.summary", source_column="order_id", target_column="id"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.summary", source_column="amount", target_column="total"))

    result = graph_service.get_downstream(1, "raw.orders", column="id")

    assert {(e.source_table, e.source_column, e.target_table, e.target_column) for e in result} == {
        ("raw.orders", "id", "stg.orders", "order_id"),
        ("stg.orders", "order_id", "mart.summary", "id"),
    }


def test_get_upstream_column_filter_narrows_across_multiple_hops():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="order_id"))
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="amount", target_column="amount"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.summary", source_column="order_id", target_column="id"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.summary", source_column="amount", target_column="total"))

    result = graph_service.get_upstream(1, "mart.summary", column="id")

    assert {(e.source_table, e.source_column, e.target_table, e.target_column) for e in result} == {
        ("raw.orders", "id", "stg.orders", "order_id"),
        ("stg.orders", "order_id", "mart.summary", "id"),
    }


def test_get_downstream_column_filter_widens_to_table_level_after_unresolved_edge():
    # Hop 2 là 1 cạnh table-level (không rõ cột, vd SELECT *) -> từ đó về sau
    # không lọc được cột nữa, phải rơi về table-level (conservative), nhưng
    # KHÔNG được lọc nhầm ở hop 1 (nơi vẫn còn rõ cột).
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="order_id"))
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="amount", target_column="amount"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.summary"))  # table-level, không rõ cột
    graph_service.add_edge(1, _edge("mart.summary", "mart.other", source_column="unrelated_col", target_column="x"))

    result = graph_service.get_downstream(1, "raw.orders", column="id")
    tables = {e.target_table for e in result}

    assert tables == {"stg.orders", "mart.summary", "mart.other"}
    first_hop = [e for e in result if e.target_table == "stg.orders"]
    assert len(first_hop) == 1 and first_hop[0].source_column == "id"


def test_get_downstream_unknown_table_returns_empty():
    assert graph_service.get_downstream(1, "does.not_exist") == []


def test_has_cycle_false_for_dag():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.revenue"))

    assert graph_service.has_cycle(1, ) is False


def test_has_cycle_true_when_cycle_present():
    graph_service.add_edge(1, _edge("a", "b"))
    graph_service.add_edge(1, _edge("b", "c"))
    graph_service.add_edge(1, _edge("c", "a"))

    assert graph_service.has_cycle(1, ) is True


def test_add_edge_reports_whether_graph_changed():
    edge = _edge("raw.orders", "stg.orders", confidence=0.7)

    assert graph_service.add_edge(1, edge) is True
    assert graph_service.add_edge(1, edge) is False
    assert graph_service.add_edge(1, _edge("raw.orders", "stg.orders", confidence=0.9)) is True


def test_rename_table_moves_incident_edges_and_preserves_metadata():
    evidence = LineageEvidence(file_path="migration.sql", reasoning="keep me")
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders", source_column="id", target_column="id", evidence=evidence))
    graph_service.add_edge(1, _edge("stg.orders", "mart.sales", source_column="id", target_column="order_id"))

    assert graph_service.rename_table(1, "stg.orders", "stg.orders_v2") is True

    assert "stg.orders" not in graph_service.get_all_tables(1, )
    assert {(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(1, )} == {
        ("raw.orders", "stg.orders_v2"),
        ("stg.orders_v2", "mart.sales"),
    }
    preserved = graph_service.get_downstream(1, "raw.orders")[0]
    assert preserved.evidence == evidence


def test_rename_table_merges_duplicate_edges_and_is_idempotent():
    graph_service.add_edge(1, _edge("raw.orders", "stg.old", confidence=0.9))
    graph_service.add_edge(1, _edge("raw.orders", "stg.new", confidence=0.7))

    assert graph_service.rename_table(1, "stg.old", "stg.new") is True
    assert graph_service.rename_table(1, "stg.old", "stg.new") is False
    assert graph_service.rename_table(1, "stg.new", "stg.new") is False
    assert len(graph_service.get_all_edges(1, )) == 1
    assert graph_service.get_all_edges(1, )[0].confidence == 0.9


def test_rename_table_remaps_both_ends_of_a_self_loop():
    graph_service.add_edge(1, _edge("a", "a"))

    assert graph_service.rename_table(1, "a", "b") is True
    assert graph_service.get_all_tables(1, ) == ["b"]
    assert [(edge.source_table, edge.target_table) for edge in graph_service.get_all_edges(1, )] == [("b", "b")]


def test_drop_table_removes_incident_edges_and_is_idempotent():
    graph_service.add_edge(1, _edge("raw.orders", "stg.orders"))
    graph_service.add_edge(1, _edge("stg.orders", "mart.sales"))

    assert graph_service.drop_table(1, "stg.orders") is True
    assert graph_service.drop_table(1, "stg.orders") is False
    assert graph_service.get_all_edges(1, ) == []
