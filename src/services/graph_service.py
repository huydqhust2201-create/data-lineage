from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

import networkx as nx

from src.models.schemas import LineageEdge, LineageEvidence
from src.services import storage_service

# Owner: Lê Huy Hoàng (PRD.md mục 11)
# NetworkX cho MVP (PRD.md mục 8). Đồ thị tách biệt hoàn toàn khỏi DB nguồn.
#
# Model: node = tên bảng; mỗi LineageEdge là 1 cạnh song song (MultiDiGraph)
# giữa source_table -> target_table, thông tin cột/transform nằm trong edge
# attributes. Cần MultiDiGraph vì 1 cặp bảng có thể có nhiều cạnh khác nhau
# (mỗi cột nguồn/đích một cạnh riêng), và cạnh table-level (column=None) vẫn
# tồn tại song song với cạnh column-level.
#
# Lọc theo cột (US-5/US-6): lan truyền qua nhiều hop — mỗi node mang theo tập
# cột "đang bị ảnh hưởng" tại chính node đó (active_columns), tính từ cột đích
# (xuôi)/cột nguồn (ngược) của cạnh vừa đi qua để tới node đó. Cạnh nào có cột
# nguồn/đích khớp tập active hiện tại (hoặc None, tức "cả bảng" — không rõ
# cột) mới được đi tiếp; gặp 1 cạnh không rõ cột thì từ đó về sau coi như
# không lọc được nữa (rơi về table-level, conservative — không bao giờ loại
# trừ khi không chắc).

_graphs: dict[int, nx.MultiDiGraph] = {}
_commit_lock = RLock()


def _get_graph(database_id: int) -> nx.MultiDiGraph:
    if database_id not in _graphs:
        _graphs[database_id] = storage_service.load(database_id)
    return _graphs[database_id]


def _reset_graph(database_id: int, graph: nx.MultiDiGraph | None = None) -> None:
    """Test-only hook: thay graph in-memory hiện tại (hoặc xoá để load lại từ đĩa)."""
    if graph is None:
        _graphs.pop(database_id, None)
    else:
        _graphs[database_id] = graph


def snapshot(database_id: int) -> nx.MultiDiGraph:
    """Return a detached copy of the live graph for what-if simulation."""
    return _get_graph(database_id).copy()


@contextmanager
def commit_lock() -> Iterator[None]:
    """Serialize copy-then-swap writes inside one Python process."""
    with _commit_lock:
        yield


def replace_graph(database_id: int, graph: nx.MultiDiGraph) -> None:
    """Atomically replace the process-local graph after a DB commit."""
    _graphs[database_id] = graph


def clear(database_id: int) -> None:
    """Xoá toàn bộ đồ thị lineage đã tích luỹ (kể cả trên Postgres).

    Ingest luôn CỘNG DỒN theo thiết kế (nhiều lần ingest riêng biệt phải gộp
    thành 1 đồ thị lineage toàn dự án) — hàm này là lối thoát thủ công cho
    người dùng chủ động muốn bắt đầu lại từ đầu (vd đổi sang test/demo với dữ
    liệu khác), gọi qua DELETE /graph. Khác _reset_graph() (chỉ test, không
    đụng Postgres).
    """
    _graphs[database_id] = nx.MultiDiGraph()
    persist(database_id)


def _edge_attrs(edge: LineageEdge) -> dict:
    attrs = {
        "transform_type": edge.transform_type,
        "confidence": edge.confidence,
        "source_type": edge.source_type,
    }
    if edge.dependency_kind != "output":
        attrs["dependency_kind"] = edge.dependency_kind
    if edge.source_column is not None:
        attrs["source_column"] = edge.source_column
    if edge.target_column is not None:
        attrs["target_column"] = edge.target_column
    if edge.evidence is not None:
        # dict thuần JSON-safe (mode="json") để tương thích khi persist xuống
        # Postgres (storage_service dùng psycopg2.extras.Json/json.dumps, không
        # tự serialize được datetime thô) — quan trọng từ khi có confirmed_at.
        attrs["evidence"] = edge.evidence.model_dump(mode="json")
    return attrs


def _attrs_to_edge(source_table: str, target_table: str, attrs: dict) -> LineageEdge:
    evidence_data = attrs.get("evidence")
    return LineageEdge(
        source_table=source_table,
        source_column=attrs.get("source_column"),
        target_table=target_table,
        target_column=attrs.get("target_column"),
        dependency_kind=attrs.get("dependency_kind", "output"),
        transform_type=attrs.get("transform_type", "unknown"),
        confidence=float(attrs.get("confidence", 1.0)),
        source_type=attrs.get("source_type", "parser"),
        evidence=LineageEvidence(**evidence_data) if evidence_data else None,
    )


def add_edge(database_id: int, edge: LineageEdge, graph: nx.MultiDiGraph | None = None) -> bool:
    """Ghi 1 cạnh đã xác nhận (confirmed_edges) vào đồ thị lineage chính thức.

    Chỉ gọi hàm này với cạnh đã qua HITL (nếu confidence thấp) hoặc
    confidence >= threshold — không gọi trực tiếp với pending_review.
    """
    graph = graph if graph is not None else _get_graph(database_id)

    found_key = None
    existing_attrs = None

    if graph.has_edge(edge.source_table, edge.target_table):
        for key, attrs in graph[edge.source_table][edge.target_table].items():
            if (
                attrs.get("source_column") == edge.source_column
                and attrs.get("target_column") == edge.target_column
                and attrs.get("source_type") == edge.source_type
                and attrs.get("dependency_kind", "output") == edge.dependency_kind
            ):
                found_key = key
                existing_attrs = attrs
                break

    if found_key is not None:
        old_confidence = float(existing_attrs.get("confidence", 1.0))
        if edge.confidence > old_confidence:
            new_attrs = _edge_attrs(edge)
            for k, v in new_attrs.items():
                graph[edge.source_table][edge.target_table][found_key][k] = v
            return True
        return False

    graph.add_edge(edge.source_table, edge.target_table, **_edge_attrs(edge))
    return True


def rename_table(database_id: int, old: str, new: str, graph: nx.MultiDiGraph | None = None) -> bool:
    """Rename a graph node while preserving all incoming/outgoing edge metadata.

    The operation is idempotent: absent nodes and ``old == new`` are no-ops.
    Edges are rebuilt through :func:`add_edge` so merging into an existing
    ``new`` node uses the service's normal deduplication contract.
    """
    graph = graph if graph is not None else _get_graph(database_id)
    if old == new or old not in graph:
        return False

    replacement_edges = []
    for source, target, _, attrs in graph.in_edges(old, keys=True, data=True):
        replacement_edges.append(
            _attrs_to_edge(new if source == old else source, new if target == old else target, attrs)
        )
    for source, target, _, attrs in graph.out_edges(old, keys=True, data=True):
        replacement_edges.append(
            _attrs_to_edge(new if source == old else source, new if target == old else target, attrs)
        )

    graph.remove_node(old)
    for edge in replacement_edges:
        add_edge(database_id, edge, graph=graph)
    return True


def drop_table(database_id: int, name: str, graph: nx.MultiDiGraph | None = None) -> bool:
    """Remove a table node and all incident lineage edges, if it exists."""
    graph = graph if graph is not None else _get_graph(database_id)
    if name not in graph:
        return False
    graph.remove_node(name)
    return True


def _traverse(
    database_id: int, table: str, column: str | None, *, downstream: bool, depth: int | None = None
) -> list[tuple[LineageEdge, int]]:
    """Trả về từng cạnh kèm `hops`: số bước từ `table` gốc tới cạnh đó (cạnh
    xuất phát thẳng từ node gốc = hop 1). Dùng cho impact analysis để nhóm
    kết quả theo tầng — 1 bảng có 8-9 tầng phụ thuộc thì FE hiển thị được
    theo từng tầng thay vì 1 danh sách phẳng lẫn lộn.
    """
    graph = _get_graph(database_id)
    if table not in graph:
        return []

    # filter_attr: cột của cạnh phải khớp active_columns tại node hiện tại để
    # được đi tiếp. produced_attr: cột mà cạnh đó "ghi vào" node kế tiếp, dùng
    # làm active_columns khởi tạo cho node đó.
    filter_attr = "source_column" if downstream else "target_column"
    produced_attr = "target_column" if downstream else "source_column"
    collected: list[tuple[LineageEdge, int]] = []
    seen_edges: set[tuple[str, str, int]] = set()
    # None = không giới hạn cột (node gốc khi query không lọc theo cột, hoặc
    # đã lan tới đây qua 1 cạnh không rõ cột) — từ đây mọi cạnh đi qua node
    # này đều được tính, không lọc tiếp.
    active_columns: dict[str, set[str] | None] = {table: ({column} if column is not None else None)}
    node_depth: dict[str, int] = {table: 0}
    visited_nodes = {table}
    queue: deque[str] = deque([table])

    while queue:
        node = queue.popleft()
        node_columns = active_columns[node]
        edge_hop = node_depth[node] + 1
        edges = (
            graph.out_edges(node, keys=True, data=True) if downstream else graph.in_edges(node, keys=True, data=True)
        )
        for u, v, key, attrs in edges:
            edge_column = attrs.get(filter_attr)
            if node_columns is not None and edge_column is not None and edge_column not in node_columns:
                continue
            edge_id = (u, v, key)
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                collected.append((_attrs_to_edge(u, v, attrs), edge_hop))
            neighbor = v if downstream else u
            neighbor_column = attrs.get(produced_attr)
            if neighbor not in visited_nodes and (depth is None or edge_hop < depth):
                visited_nodes.add(neighbor)
                active_columns[neighbor] = None if node_columns is None or neighbor_column is None else {neighbor_column}
                node_depth[neighbor] = edge_hop
                queue.append(neighbor)
            elif neighbor in visited_nodes and active_columns[neighbor] is not None and neighbor_column is not None:
                # Node đã trong hàng đợi (chưa xử lý) nhưng gặp thêm 1 cạnh
                # song song khác đóng góp cột — gộp vào cùng 1 lượt duyệt.
                active_columns[neighbor].add(neighbor_column)

    return collected


def get_downstream(database_id: int, table: str, column: str | None = None) -> list[LineageEdge]:
    """Duyệt xuôi (BFS/DFS): trả về mọi bảng/cột bị ảnh hưởng nếu sửa table.column này.

    Dùng cho US-5 (impact analysis khi sửa/xoá cột).
    """
    return [edge for edge, _hops in _traverse(database_id, table, column, downstream=True)]


def get_upstream(database_id: int, table: str, column: str | None = None) -> list[LineageEdge]:
    """Duyệt ngược: trả về table.column này được tính từ đâu.

    Dùng cho US-6 (debug số liệu sai).
    """
    return [edge for edge, _hops in _traverse(database_id, table, column, downstream=False)]


def get_downstream_with_hops(
    database_id: int, table: str, column: str | None = None, depth: int | None = None
) -> list[tuple[LineageEdge, int]]:
    """Như get_downstream, kèm số hop từ table gốc — dùng cho impact analysis
    hiển thị theo tầng (sub-graph tập trung theo từng hop)."""
    return _traverse(database_id, table, column, downstream=True, depth=depth)


def get_upstream_with_hops(
    database_id: int, table: str, column: str | None = None, depth: int | None = None
) -> list[tuple[LineageEdge, int]]:
    """Như get_upstream, kèm số hop từ table gốc."""
    return _traverse(database_id, table, column, downstream=False, depth=depth)


def has_cycle(database_id: int) -> bool:
    """Kiểm tra đồ thị hiện tại có chu trình không (dữ liệu lineage hợp lệ phải là DAG)."""
    return not nx.is_directed_acyclic_graph(_get_graph(database_id))


def get_all_edges(database_id: int) -> list[LineageEdge]:
    """Toàn bộ cạnh đã xác nhận trong đồ thị — dùng cho GET /graph (FR-7).

    """
    graph = _get_graph(database_id)
    edges = [_attrs_to_edge(u, v, attrs) for u, v, attrs in graph.edges(data=True)]
    return edges


def get_all_tables(database_id: int) -> list[str]:
    """Toàn bộ tên bảng (node) trong đồ thị — dùng cho GET /graph (FR-7)."""
    return list(_get_graph(database_id).nodes)


def persist(database_id: int) -> None:
    """Ghi đồ thị hiện tại xuống Postgres — gọi sau khi add_edge() 1 batch (FR-5)."""
    storage_service.save(database_id, _get_graph(database_id))
