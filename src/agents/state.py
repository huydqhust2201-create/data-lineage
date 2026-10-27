from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from src.agents.chat.base import edge_fingerprint
from src.models.schemas import GraphEvent, LineageEdge


class LineageAgentState(TypedDict, total=False):
    """State schema cho pipeline lineage: parse -> extract -> validate(HITL) -> build_graph -> answer.

    Mỗi field ứng với 1 bước; node nào đọc/ghi field nào xem PRD.md mục 6 (FR-1..FR-7).
    """

    input_path: str  # bắt buộc: folder/repo do user cung cấp (FR-1, không tự dò tìm)
    database_id: int
    sql_files: list[str]  # danh sách file .sql/dbt model tìm thấy trong input_path
    parsed_edges: list[LineageEdge]  # kết quả sqlglot/sqllineage, source_type="parser" (FR-2)
    graph_events: Annotated[list[GraphEvent], operator.add]  # tác động graph theo thứ tự SQL
    unparsed_files: list[str]  # file parser fail, cần đưa qua LLM (FR-3)
    fallback_reasons: dict[str, str]  # file_path -> lý do parser fail (evidence.fallback_reason)
    llm_edges: list[LineageEdge]  # kết quả LLM extraction, source_type="llm" (FR-3)
    pending_review: list[LineageEdge]  # cạnh confidence < ngưỡng, chờ HITL xác nhận (FR-4)
    confirmed_edges: list[LineageEdge]  # đã xác nhận, sẵn sàng ghi vào graph (FR-5)
    error: str | None
    cycle_detected: bool | None
    breaking_changes_detected: int  # bảng bị drop/rename nhưng vẫn còn downstream tham chiếu
    descriptions_written: int
    descriptions_pending: int
    sql_documents_written: int  # số chunk SQL (RAG) mới/đổi đã embed lại lượt ingest này


def dedupe_edges(left: list[LineageEdge], right: list[LineageEdge]) -> list[LineageEdge]:
    """Merge edges by stable fingerprint, never by transient graph edge ids."""

    merged: list[LineageEdge] = []
    seen = set()
    for edge in [*left, *right]:
        key = edge_fingerprint(edge)
        if key not in seen:
            seen.add(key)
            merged.append(edge)
    return merged


class ChatAgentState(TypedDict, total=False):
    """Accumulated state for the bounded lineage chat tool loop."""

    question: str
    database_id: int
    messages: Annotated[list[AnyMessage], add_messages]
    steps: Annotated[list[dict[str, Any]], operator.add]
    confirmed: Annotated[list[LineageEdge], dedupe_edges]
    pending: Annotated[list[LineageEdge], dedupe_edges]
    vocabulary: Annotated[set[str], operator.or_]
    hops: Annotated[dict[str, int], operator.or_]
    risk: Annotated[dict[str, str], operator.or_]
    assets: Annotated[dict[str, Any], operator.or_]
    breaking_changes: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    history: str
    clarification: dict[str, Any] | None
    pinned_table: str | None
    tool_calls_used: int
    agent_steps_used: int
    answer: str
    resolved: dict[str, Any]
    query_columns: list[dict[str, Any]]
    matched_columns: list[dict[str, Any]]
    last_resolved_table: str | None
