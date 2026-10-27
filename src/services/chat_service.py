"""HTTP-facing orchestration for the bounded lineage chat graph."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, HumanMessage

from src import metrics
from src.agents.chat.registry import REGISTRY
from src.agents.chat.resolve import match_clarification, question_with_choice
from src.agents.chat.session import (
    PendingClarification,
    Turn,
    get_or_create,
    recent_turns,
    save_turn,
    set_clarification,
)
from src.agents.graph import build_chat_graph
from src.agents.nodes.query_nodes import compose_node, verify_node
from src.config import get_settings
from src.models.schemas import ChatResponse, ChatStep, ImpactEdgeView

logger = logging.getLogger(__name__)
CHAT_TRACE_DIR = Path("logs/chat-traces")


_HISTORY_ANSWER_PREVIEW_CHARS = 300


def _history_text(turns: list[Turn]) -> str:
    """Create the short prior-turn context accepted by ``agent_node`` and ``compose_node``.

    Includes an answer preview (not just the question) so a follow-up meta-question about
    what a prior turn concluded — not only what was asked — can be answered from history alone.
    """
    lines = []
    for turn in turns:
        answer_preview = turn.answer[:_HISTORY_ANSWER_PREVIEW_CHARS]
        if len(turn.answer) > _HISTORY_ANSWER_PREVIEW_CHARS:
            answer_preview += "..."
        lines.append(
            f'[lượt trước] Hỏi: "{turn.question}" | bảng đã chốt: {turn.resolved_table or "không có"} | '
            f'Đã trả lời: "{answer_preview}"'
        )
    return "\n".join(lines)


def _last_resolved_table(turns: list[Turn]) -> str | None:
    return next((turn.resolved_table for turn in reversed(turns) if turn.resolved_table), None)


def _run_resume(chosen_table: str, clarification: PendingClarification, database_id: int, history: str) -> dict[str, Any]:
    """Run the previously blocked capability without asking the agent LLM again."""
    capability = REGISTRY.get(clarification.resume_tool)
    if capability is None:
        return {"question": clarification.question, "warnings": ["resume_tool_unavailable"]}

    started_at = time.monotonic()
    params = capability.Params.model_validate(clarification.resume_args | {clarification.slot: chosen_table})
    result = capability.run(params, database_id)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    resolved = result.extra
    step_resolved = None
    if result.error is None:
        step_resolved = {
            "table": result.extra.get("resolved_table"),
            "column": result.extra.get("resolved_column"),
            "direction": result.extra.get("direction"),
        }
    state: dict[str, Any] = {
        "question": clarification.question,
        "database_id": database_id,
        "history": history,
        "confirmed": result.confirmed,
        "pending": result.pending,
        "vocabulary": capability.vocabulary(result),
        "resolved": resolved,
        "tool_calls_used": 1,
        "steps": [
            {
                "tool": capability.name,
                "args": clarification.resume_args | {clarification.slot: chosen_table},
                "resolved": step_resolved,
                "error": result.error,
                "summary": _step_summary(result),
                "duration_ms": duration_ms,
                "agent_step": 0,
            }
        ],
    }
    if result.extra.get("hops_by_edge"):
        state["hops"] = result.extra["hops_by_edge"]
    return _compose_and_verify(state)


def _compose_and_verify(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the final two deterministic graph stages for a direct resume."""
    composed = compose_node(cast(Any, state))
    merged = {**state, **composed}
    verified = verify_node(cast(Any, merged))
    if verified:
        merged.update(verified)
        merged["warnings"] = [*state.get("warnings", []), *composed.get("warnings", []), *verified.get("warnings", [])]
    elif composed.get("warnings"):
        merged["warnings"] = [*state.get("warnings", []), *composed["warnings"]]
    return merged


def _step_summary(result: Any) -> str:
    """Expose concise operational metadata without forwarding a raw tool payload."""
    if result.error:
        return result.error
    return f"{len(result.confirmed)} confirmed, {len(result.pending)} pending"


def _steps(state: dict[str, Any]) -> list[ChatStep]:
    steps: list[ChatStep] = []
    for step in state.get("steps", []):
        summary = step.get("summary", "")
        if summary.startswith("{"):
            try:
                payload = json.loads(summary)
                if payload.get("ok"):
                    # Các capability khác nhau trả "confirmed"/"pending" ở 2 hình dạng:
                    # dict {"count": N, "tables": [...]} (downstream/upstream) hoặc list
                    # thẳng các edge (list_relationships) — đếm được cả 2, không giả định
                    # cứng 1 hình dạng như trước (từng ném KeyError, rơi về "tool completed").
                    def _count(value: Any) -> int:
                        if isinstance(value, dict):
                            return int(value.get("count", 0))
                        if isinstance(value, list):
                            return len(value)
                        return 0

                    summary = f"{_count(payload.get('confirmed'))} confirmed, {_count(payload.get('pending'))} pending"
                else:
                    summary = str(payload.get("error", "tool_failed"))
            except (TypeError, ValueError, KeyError):
                summary = "tool completed"
        steps.append(
            ChatStep(
                tool=step["tool"],
                args=step["args"],
                resolved=step.get("resolved"),
                error=step.get("error"),
                summary=summary,
                duration_ms=step["duration_ms"],
                agent_step=step["agent_step"],
            )
        )
    return steps


def _pending_clarification(value: dict[str, Any] | None) -> PendingClarification | None:
    if value is None:
        return None
    return PendingClarification(
        slot=value["slot"],
        mention=value["mention"],
        candidates=value["candidates"],
        question=value["question"],
        resume_tool=value["resume_tool"],
        resume_args=value["resume_args"],
        kind=value.get("kind", "tool"),
    )


def _response(session_id: str, state: dict[str, Any]) -> ChatResponse:
    resolved = state.get("resolved", {})
    clarification = state.get("clarification")
    return ChatResponse(
        session_id=session_id,
        answer=state.get("answer", ""),
        confirmed=[ImpactEdgeView.from_edge(edge, hitl_status="confirmed") for edge in state.get("confirmed", [])],
        inferred_pending=[ImpactEdgeView.from_edge(edge, hitl_status="pending") for edge in state.get("pending", [])],
        clarification_options=clarification.get("candidates", []) if clarification else [],
        suggestions=resolved.get("suggestions", []),
        warnings=state.get("warnings", []),
        steps=_steps(state),
        stop_reason=_stop_reason(state),
        tool_calls_used=state.get("tool_calls_used", 0),
    )


def _stop_reason(state: dict[str, Any]) -> Literal["clarification", "budget_exhausted", "completed"]:
    if state.get("clarification") is not None:
        return "clarification"

    settings = get_settings()
    if state.get("tool_calls_used", 0) >= settings.chat_max_tool_calls:
        return "budget_exhausted"

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if (
        state.get("agent_steps_used", 0) >= settings.chat_max_agent_steps
        and isinstance(last_message, AIMessage)
        and bool(last_message.tool_calls)
    ):
        return "budget_exhausted"
    return "completed"


def _append_trace(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_trace(response: ChatResponse, question: str, database_id: int) -> None:
    if not get_settings().chat_trace_enabled:
        return

    now = datetime.now(UTC)
    record = {
        "ts": now.isoformat(),
        "session_id": response.session_id,
        "database_id": database_id,
        "question": question,
        "answer": response.answer,
        "steps": [step.model_dump(mode="json") for step in response.steps],
        "stop_reason": response.stop_reason,
        "tool_calls_used": response.tool_calls_used,
        "warnings": response.warnings,
    }
    try:
        _append_trace(CHAT_TRACE_DIR / f"{now.date().isoformat()}.jsonl", record)
    except Exception:
        logger.exception("chat_trace_write_failed session_id=%s", response.session_id)
        response.warnings.append("chat_trace_write_failed")


def _initial_chat_state(question: str, database_id: int, history: str, last_table: str | None) -> dict[str, Any]:
    return {
        "question": question,
        "database_id": database_id,
        "messages": [HumanMessage(content=question)],
        "history": history,
        "last_resolved_table": last_table,
    }


def answer_question_stream(question: str, user_id: int, database_id: int) -> Iterator[dict[str, Any]]:
    """Yield grounded chat progress; persist the completed turn immediately before ``done``."""
    """Run a chat turn against the calling user's single ongoing thread for this
    database — identity is (database_id, user_id), not a client-supplied session id
    (xem src/agents/chat/session.py: 1 luồng liên tục / user, giống Claude Code)."""
    session = get_or_create(database_id, user_id)
    turns = recent_turns(database_id, user_id, get_settings().chat_max_history_turns)
    history = _history_text(turns)
    last_table = _last_resolved_table(turns)
    try:
        resume = session.pending_clarification
        if resume and (chosen := match_clarification(question, resume.candidates)) is not None and resume.kind == "tool":
            state = _run_resume(chosen, resume, database_id, history)
            for step in _steps(state):
                yield {"event": "step", "data": step}
        else:
            if resume and (chosen := match_clarification(question, resume.candidates)) is not None:
                resumed = question_with_choice(resume.question, resume.mention, chosen)
                state = _initial_chat_state(resumed, database_id, history, last_table)
                state["pinned_table"] = chosen
            else:
                state = _initial_chat_state(question, database_id, history, last_table)
            emitted_steps = 0
            emitted_thoughts = 0
            metrics.record_llm_call("chat")
            for mode, payload in build_chat_graph().stream(state, stream_mode=["values", "messages"]):
                if mode == "values":
                    state = payload
                    steps = _steps({"steps": state.get("steps", [])})
                    for step in steps[emitted_steps:]:
                        yield {"event": "step", "data": step}
                    emitted_steps = len(steps)
                    messages = state.get("messages", [])
                    if len(messages) > emitted_thoughts:
                        message = messages[-1]
                        content = str(getattr(message, "content", "")).strip()
                        if content and content.upper() != "DONE" and isinstance(message, AIMessage):
                            yield {"event": "thought", "data": {"text": content, "agent_step": state.get("agent_steps_used", 0)}}
                        emitted_thoughts = len(messages)
                elif mode == "messages":
                    chunk, metadata = payload
                    if metadata.get("langgraph_node") == "compose" and get_settings().chat_verify_mode == "warn":
                        content = str(getattr(chunk, "content", ""))
                        if content:
                            yield {"event": "token", "data": {"text": content}}

        pending = _pending_clarification(state.get("clarification"))
        set_clarification(database_id, user_id, pending)
        response = _response(str(user_id), state)
        _write_trace(response, question, database_id)
        save_turn(database_id, user_id, question, state.get("resolved", {}).get("resolved_table"), response.answer)
        logger.info("chat_response user_id=%s database_id=%s steps=%d", user_id, database_id, len(response.steps))
        yield {"event": "done", "data": response}
    except Exception as exc:
        logger.exception("chat_stream_failed user_id=%s database_id=%s", user_id, database_id)
        yield {"event": "error", "data": {"detail": str(exc)}}


def answer_question(question: str, user_id: int, database_id: int) -> ChatResponse:
    for event in answer_question_stream(question, user_id, database_id):
        if event["event"] == "done":
            return cast(ChatResponse, event["data"])
        if event["event"] == "error":
            raise RuntimeError(cast(dict[str, str], event["data"])["detail"])
    raise RuntimeError("chat stream ended without done event")
