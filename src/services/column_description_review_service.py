"""In-memory HITL queue for low-confidence column descriptions."""

from src.models.schemas import PendingColumnDescription

_pending: dict[int, dict[str, PendingColumnDescription]] = {}


def _key(node_id: int, column: str) -> str:
    return f"{node_id}:{column}"


def add_pending(database_id: int, items: list[PendingColumnDescription]) -> None:
    for item in items:
        _pending.setdefault(database_id, {})[_key(item.node_id, item.column)] = item


def list_pending(database_id: int) -> list[PendingColumnDescription]:
    return list(_pending.get(database_id, {}).values())


def pop_pending(database_id: int, node_id: int, column: str) -> PendingColumnDescription | None:
    return _pending.get(database_id, {}).pop(_key(node_id, column), None)


def clear_pending(database_id: int) -> None:
    _pending.pop(database_id, None)


def _reset() -> None:
    _pending.clear()
