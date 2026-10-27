"""Chat capabilities backed by the shared lineage graph vocabulary."""

from __future__ import annotations

from difflib import get_close_matches
from typing import Literal

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.agents.chat.resolve import is_known_column, known_tables, normalize
from src.config import get_settings
from src.services import graph_service, review_service


class SearchTablesParams(BaseModel):
    query: str | None = None
    limit: int | None = Field(default=None, ge=1)


class SearchTablesCapability:
    """Expose a bounded, trusted table-name discovery tool to the agent."""

    name = "search_tables"
    description = "List real table names in the lineage graph, optionally filtered by a fragment."
    Params = SearchTablesParams

    def run(self, params: SearchTablesParams, database_id: int) -> CapabilityResult:
        tables = known_tables(database_id)
        configured_limit = get_settings().chat_search_limit
        limit = min(params.limit or configured_limit, configured_limit)
        if params.query:
            query = normalize(params.query)
            matching = [table for table in tables if query in normalize(table)]
            if len(matching) == 1:
                return CapabilityResult(extra={"tables": matching, "truncated": False, "total": 1})
            if len(matching) > 1:
                return CapabilityResult(
                    error="needs_selection", extra={"mention": params.query, "candidates": matching}
                )
            if is_known_column(database_id, params.query):
                return CapabilityResult(error="is_a_column", extra={"column_mention": params.query})
            # get_close_matches raises ValueError for n=0; an empty graph has no suggestions.
            fuzzy = (
                set(get_close_matches(query, [normalize(table) for table in tables], n=len(tables), cutoff=0.6))
                if tables
                else set()
            )
            suggestions = [table for table in tables if normalize(table) in fuzzy]
            return CapabilityResult(
                error="table_not_found", extra={"mention": params.query, "suggestions": suggestions}
            )
        return CapabilityResult(
            extra={"tables": tables[:limit], "truncated": len(tables) > limit, "total": len(tables)}
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        return set(result.extra.get("tables", [])) | set(result.extra.get("candidates", [])) | set(result.extra.get("suggestions", []))

    def prompt_rules(self) -> str:
        return "Use search_tables only to discover table names. For a column mention, call traverse directly."

    def template(self, result: CapabilityResult) -> str:
        return "Available tables: " + ", ".join(result.extra.get("tables", []))


SEARCH_TABLES_CAPABILITY = SearchTablesCapability()


class ListRelationshipsParams(BaseModel):
    status: Literal["pending", "confirmed", "all"] = "pending"
    limit: int | None = Field(default=None, ge=1)


class ListRelationshipsCapability:
    """Expose already-known lineage edges directly, without requiring a table name.

    downstream/upstream/search_tables đều cần biết trước 1 tên bảng cụ thể
    — không tool nào trả lời được câu hỏi tổng quát kiểu "liệt kê hết cạnh
    đang pending" hay "vừa ingest được gì". Thiếu tool này khiến agent hết
    budget mà chưa từng đọc được cạnh nào, rồi báo sai là "không có dữ liệu"
    dù graph/pending_review thực sự có edge.
    """

    name = "list_relationships"
    description = (
        "List lineage relationships (edges) already known to the system, filtered by review "
        "status (pending/confirmed/all). Use this for broad questions with no specific table "
        "named — e.g. 'what is pending', 'what did the last ingest find', 'list relationships'."
    )
    Params = ListRelationshipsParams

    def run(self, params: ListRelationshipsParams, database_id: int) -> CapabilityResult:
        configured_limit = get_settings().chat_search_limit
        limit = min(params.limit or configured_limit, configured_limit)

        all_confirmed = graph_service.get_all_edges(database_id) if params.status in ("confirmed", "all") else []
        all_pending = review_service.list_pending(database_id) if params.status in ("pending", "all") else []

        return CapabilityResult(
            confirmed=all_confirmed[:limit],
            pending=all_pending[:limit],
            extra={
                "total_confirmed": len(all_confirmed),
                "total_pending": len(all_pending),
                "truncated": len(all_confirmed) > limit or len(all_pending) > limit,
            },
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        tables: set[str] = set()
        for edge in [*result.confirmed, *result.pending]:
            tables.update((edge.source_table, edge.target_table))
        return tables

    def prompt_rules(self) -> str:
        return (
            "Use list_relationships (not search_tables) when the question is about relationships "
            "in general — pending review status, or what was just ingested — with no table named."
        )

    def template(self, result: CapabilityResult) -> str:
        confirmed_n = len(result.confirmed)
        pending_n = len(result.pending)
        return f"{confirmed_n} confirmed, {pending_n} pending relationship(s) trong hệ thống"


LIST_RELATIONSHIPS_CAPABILITY = ListRelationshipsCapability()
