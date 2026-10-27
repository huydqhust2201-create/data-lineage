"""Benchmark cho tiêu chí PRD §Success Metrics: 'Impact query đủ nhanh để dùng
tương tác — latency truy vấn downstream/upstream < 3s trên đồ thị demo'.

Không phải test correctness (đã có ở test_graph_service.py/test_routes.py) —
chỉ canh regression latency khi ai đó vô tình đổi _traverse() thành thuật
toán chậm hơn (vd O(n^2) thay vì BFS O(V+E)). Đồ thị dựng ở đây lớn hơn hẳn
đồ thị demo thật (~60 cạnh) để có biên độ an toàn thay vì chỉ vừa đủ pass.
"""

import time

import pytest

from src.models.schemas import LineageEdge
from src.services import graph_service, impact_service

_DATABASE_ID = 1


@pytest.fixture(autouse=True)
def fresh_graph():
    import networkx as nx

    graph_service._reset_graph(_DATABASE_ID, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(_DATABASE_ID, None)


def _edge(source_table: str, target_table: str, column: str) -> LineageEdge:
    return LineageEdge(
        source_table=source_table,
        source_column=column,
        target_table=target_table,
        target_column=column,
        confidence=1.0,
        source_type="parser",
        transform_type="direct",
    )


def _build_wide_deep_graph(depth: int = 8, fanout: int = 12) -> None:
    """Chain `depth` tầng, mỗi tầng fan-out `fanout` bảng con — mô phỏng 1
    warehouse thật (staging -> intermediate -> nhiều mart/dashboard song song),
    lớn hơn nhiều lần đồ thị demo (29 node/57 cạnh thấy trong phiên làm việc)."""
    for level in range(depth):
        parents = [f"t{level}_{i}" for i in range(fanout)] if level > 0 else ["root"]
        for p in parents:
            for i in range(fanout):
                child = f"t{level + 1}_{i}"
                graph_service.add_edge(_DATABASE_ID, _edge(p, child, "id"))


def test_downstream_impact_query_completes_under_3s_on_large_graph():
    _build_wide_deep_graph(depth=8, fanout=12)

    started = time.perf_counter()
    result = impact_service.query_impact(_DATABASE_ID, "root", column="id", direction="downstream")
    elapsed = time.perf_counter() - started

    assert len(result.confirmed) > 0
    assert elapsed < 3.0, f"GET /impact downstream mất {elapsed:.2f}s trên đồ thị lớn — vượt tiêu chí PRD (<3s)"


def test_upstream_impact_query_completes_under_3s_on_large_graph():
    _build_wide_deep_graph(depth=8, fanout=12)
    leaf = "t8_0"

    started = time.perf_counter()
    result = impact_service.query_impact(_DATABASE_ID, leaf, column="id", direction="upstream")
    elapsed = time.perf_counter() - started

    assert len(result.confirmed) > 0
    assert elapsed < 3.0, f"GET /impact upstream mất {elapsed:.2f}s trên đồ thị lớn — vượt tiêu chí PRD (<3s)"
