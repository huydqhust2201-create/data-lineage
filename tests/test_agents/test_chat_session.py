from datetime import UTC, datetime

import pytest

from src.agents.chat import session
from src.services import storage_service


@pytest.fixture(autouse=True)
def fake_chat_storage(monkeypatch):
    """Giả lập chat_sessions/chat_turns bằng dict/list RAM — session.py giờ
    đọc/ghi thẳng qua storage_service (Postgres thật), test này không cần
    Postgres."""
    sessions: dict[tuple[int, int], dict | None] = {}
    turns: list[dict] = []

    def fake_ensure(database_id, user_id, tx=None):
        sessions.setdefault((database_id, user_id), None)

    def fake_get(database_id, user_id, tx=None):
        if (database_id, user_id) not in sessions:
            return None
        return storage_service.ChatSessionRow(
            database_id=database_id,
            user_id=user_id,
            pending_clarification=sessions[(database_id, user_id)],
            updated_at=datetime.now(UTC),
        )

    def fake_set_clarification(database_id, user_id, pending_clarification, tx=None):
        sessions[(database_id, user_id)] = pending_clarification

    def fake_insert_turn(database_id, user_id, question, resolved_table, answer, tx=None):
        turns.append(
            {
                "database_id": database_id,
                "user_id": user_id,
                "question": question,
                "resolved_table": resolved_table,
                "answer": answer,
            }
        )

    def fake_list_recent(database_id, user_id, limit, tx=None):
        matching = [t for t in turns if t["database_id"] == database_id and t["user_id"] == user_id]
        recent = matching[-limit:]
        return [
            storage_service.ChatTurnRow(
                id=i,
                database_id=t["database_id"],
                user_id=t["user_id"],
                question=t["question"],
                resolved_table=t["resolved_table"],
                answer=t["answer"],
                created_at=datetime.now(UTC),
            )
            for i, t in enumerate(recent)
        ]

    def fake_clear(database_id, user_id, tx=None):
        turns[:] = [t for t in turns if not (t["database_id"] == database_id and t["user_id"] == user_id)]
        sessions[(database_id, user_id)] = None

    monkeypatch.setattr(session.storage_service, "ensure_chat_session", fake_ensure)
    monkeypatch.setattr(session.storage_service, "get_chat_session", fake_get)
    monkeypatch.setattr(session.storage_service, "set_chat_session_clarification", fake_set_clarification)
    monkeypatch.setattr(session.storage_service, "insert_chat_turn", fake_insert_turn)
    monkeypatch.setattr(session.storage_service, "list_recent_chat_turns", fake_list_recent)
    monkeypatch.setattr(session.storage_service, "clear_chat_session", fake_clear)
    yield {"sessions": sessions, "turns": turns}


def test_get_or_create_returns_same_identity_for_same_user():
    created = session.get_or_create(1, 42)
    assert created.database_id == 1
    assert created.user_id == 42
    assert created.pending_clarification is None

    again = session.get_or_create(1, 42)
    assert again.user_id == 42
    assert again.pending_clarification is None


def test_get_or_create_is_isolated_per_user_and_database():
    session.get_or_create(1, 1)
    session.save_turn(1, 1, "q1", "orders", "a1")
    session.get_or_create(1, 2)
    session.save_turn(1, 2, "q2", "customers", "a2")

    assert [t.question for t in session.recent_turns(1, 1, 10)] == ["q1"]
    assert [t.question for t in session.recent_turns(1, 2, 10)] == ["q2"]


def test_save_turn_is_append_only_and_ordered():
    session.get_or_create(1, 1)
    for index in range(3):
        session.save_turn(1, 1, str(index), "orders", "answer")
    assert [t.question for t in session.recent_turns(1, 1, 10)] == ["0", "1", "2"]


def test_recent_turns_respects_limit_and_keeps_order():
    session.get_or_create(1, 1)
    for index in range(5):
        session.save_turn(1, 1, str(index), "orders", "answer")
    assert [t.question for t in session.recent_turns(1, 1, 2)] == ["3", "4"]


def test_set_clarification_and_get_or_create_reflect_it():
    session.get_or_create(1, 1)
    clarification = session.PendingClarification("table", "orders", ["stg.orders"], "question", "downstream", {})
    session.set_clarification(1, 1, clarification)

    current = session.get_or_create(1, 1)
    assert current.pending_clarification == clarification


def test_reset_clears_turns_and_clarification_but_keeps_identity():
    session.get_or_create(1, 1)
    session.save_turn(1, 1, "q1", "orders", "a1")
    session.set_clarification(1, 1, session.PendingClarification("table", "x", ["a"], "q", "downstream", {}))

    session.reset(1, 1)

    current = session.get_or_create(1, 1)
    assert current.pending_clarification is None
    assert session.recent_turns(1, 1, 10) == []
