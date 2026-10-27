from src.models.schemas import LineageEdge

# Owner: Huy — hàng đợi HITL (FR-4). In-memory, giống kiểu _graph singleton
# trong graph_service.py — đơn giản, đủ cho MVP 1 process. Không dùng LangGraph
# interrupt/checkpoint vì confirm/reject xảy ra qua 1 API call riêng, sau khi
# graph run đã kết thúc — không cần pause giữa chừng 1 lần chạy.

_pending: dict[int, dict[str, LineageEdge]] = {}


def add_pending(database_id: int, edges: list[LineageEdge]) -> None:
    """Thêm các cạnh confidence thấp vào hàng đợi chờ xác nhận."""
    for edge in edges:
        _pending.setdefault(database_id, {})[edge.edge_id] = edge


def list_pending(database_id: int) -> list[LineageEdge]:
    return list(_pending.get(database_id, {}).values())


def pop_pending(database_id: int, edge_id: str) -> LineageEdge | None:
    """Lấy ra và xoá khỏi hàng đợi — dùng khi confirm hoặc reject."""
    return _pending.get(database_id, {}).pop(edge_id, None)


def clear_pending(database_id: int) -> None:
    """Xoá toàn bộ hàng đợi HITL — dùng cùng graph_service.clear() khi user
    chủ động reset đồ thị (DELETE /graph)."""
    _pending.pop(database_id, None)


def _reset() -> None:
    """Test-only hook."""
    _pending.clear()
