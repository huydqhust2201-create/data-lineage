"""In-memory HITL queue for low-confidence table descriptions."""

from src.models.schemas import PendingDescription

_pending: dict[int, dict[str, PendingDescription]] = {}


def add_pending(database_id: int, items: list[PendingDescription]) -> None:
    for item in items:
        _pending.setdefault(database_id, {})[str(item.node_id)] = item


def list_pending(database_id: int) -> list[PendingDescription]:
    return list(_pending.get(database_id, {}).values())


def pop_pending(database_id: int, node_id: str) -> PendingDescription | None:
    return _pending.get(database_id, {}).pop(node_id, None)


def clear_pending(database_id: int) -> None:
    _pending.pop(database_id, None)


def _reset() -> None:
    _pending.clear()
