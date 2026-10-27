"""Session hội thoại chat — 1 luồng liên tục / (database_id, user_id), giống
cách Claude Code lưu conversation gắn với user/project thật thay vì UUID
sinh ngẫu nhiên per-conversation. Không có TTL/cap — session sống mãi cho
tới khi người dùng chủ động "bắt đầu lại" (reset), giống hệt việc Claude Code
resume 1 phiên cũ thay vì tự động hết hạn.

Mọi thao tác đọc/ghi đi thẳng qua storage_service (Postgres) — không có
cache RAM riêng: định danh theo user_id đã tự loại bỏ vấn đề "worker khác
không thấy session" (khác thiết kế UUID+cache RAM trước đây), nên round-trip
DB trực tiếp là đủ đơn giản và đúng, không cần lớp cache thêm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.services import storage_service


@dataclass
class PendingClarification:
    """State needed to resume one resolved table tool call without an LLM."""

    slot: Literal["table", "column"]
    mention: str
    candidates: list[str]
    question: str
    resume_tool: str
    resume_args: dict
    kind: Literal["tool", "question"] = "tool"


@dataclass
class Turn:
    """A completed exchange retained for bounded session history."""

    question: str
    resolved_table: str | None
    answer: str


@dataclass
class ChatSession:
    """Identity + pending clarification cho 1 (database_id, user_id)."""

    database_id: int
    user_id: int
    pending_clarification: PendingClarification | None


def _clarification_to_dict(clarification: PendingClarification | None) -> dict | None:
    if clarification is None:
        return None
    return {
        "slot": clarification.slot,
        "mention": clarification.mention,
        "candidates": clarification.candidates,
        "question": clarification.question,
        "resume_tool": clarification.resume_tool,
        "resume_args": clarification.resume_args,
        # Bat buoc: kind="question" nghia la "chay lai cau hoi goc voi bang da chon",
        # khac han kind="tool" (chay lai dung 1 tool). Bo qua truong nay khi luu se lam
        # moi clarification doc lai thanh "tool" -> _run_resume voi resume_tool="" -> hong.
        "kind": clarification.kind,
    }


def _clarification_from_dict(data: dict | None) -> PendingClarification | None:
    if data is None:
        return None
    return PendingClarification(**data)


def get_or_create(database_id: int, user_id: int) -> ChatSession:
    """Lấy luồng hội thoại của user này trong database này, tạo mới nếu chưa có."""
    storage_service.ensure_chat_session(database_id, user_id)
    row = storage_service.get_chat_session(database_id, user_id)
    assert row is not None
    return ChatSession(
        database_id=row.database_id,
        user_id=row.user_id,
        pending_clarification=_clarification_from_dict(row.pending_clarification),
    )


def recent_turns(database_id: int, user_id: int, limit: int) -> list[Turn]:
    """N lượt gần nhất, theo đúng thứ tự hội thoại (cũ -> mới)."""
    rows = storage_service.list_recent_chat_turns(database_id, user_id, limit)
    return [Turn(question=row.question, resolved_table=row.resolved_table, answer=row.answer) for row in rows]


def save_turn(database_id: int, user_id: int, question: str, resolved_table: str | None, answer: str) -> None:
    """Append-only — không đọc-sửa-ghi lịch sử cũ, chỉ thêm 1 dòng mới."""
    storage_service.insert_chat_turn(database_id, user_id, question, resolved_table, answer)


def set_clarification(database_id: int, user_id: int, clarification: PendingClarification | None) -> None:
    storage_service.set_chat_session_clarification(database_id, user_id, _clarification_to_dict(clarification))


def reset(database_id: int, user_id: int) -> None:
    """"Bắt đầu lại" — xoá lịch sử + clarification đang chờ, giữ nguyên định danh user."""
    storage_service.clear_chat_session(database_id, user_id)
