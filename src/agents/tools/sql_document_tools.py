"""Semantic search over raw ingested SQL text (RAG) — khác search_by_description
(tìm bảng theo mô tả LLM sinh ra): tool này tìm trực tiếp trên VĂN BẢN SQL
thật, cho câu hỏi chạm vào logic cụ thể (điều kiện WHERE/JOIN, macro...)
thay vì chỉ cấu trúc lineage."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.config import get_settings
from src.services import embedding_service, storage_service

logger = logging.getLogger(__name__)


class SearchSqlContentParams(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int | None = Field(default=None, ge=1)


class SearchSqlContentCapability:
    name = "search_sql_content"
    description = (
        "Semantic search over the raw SQL text of ingested files/models — use when the user asks "
        "about specific SQL logic, a WHERE/JOIN condition, a macro, or 'what does this file actually "
        "compute' rather than the lineage graph structure (table/column relationships)."
    )
    Params = SearchSqlContentParams

    def run(self, params: SearchSqlContentParams, database_id: int) -> CapabilityResult:
        settings = get_settings()
        if not settings.description_enabled:
            return CapabilityResult(error="descriptions_disabled")

        try:
            total = storage_service.count_searchable_sql_documents(database_id)
        except Exception:
            logger.exception("Semantic SQL content search failed")
            return CapabilityResult(error="search_unavailable")
        if total == 0:
            return CapabilityResult(error="index_empty")

        vectors = embedding_service.embed([params.query])
        if not vectors:
            return CapabilityResult(error="embedding_unavailable")

        limit = min(params.limit or settings.chat_search_limit, settings.chat_search_limit)
        try:
            matches = storage_service.search_sql_documents(database_id, vectors[0], limit)
        except Exception:
            logger.exception("Semantic SQL content search failed")
            return CapabilityResult(error="search_unavailable")
        return CapabilityResult(
            extra={
                "documents": [
                    {"file_path": file_path, "statement_order": order, "table": table_name, "content": content}
                    for file_path, order, table_name, content, _score in matches[:limit]
                ],
                "truncated": total > limit,
                "total": total,
            }
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        documents = result.extra.get("documents", [])
        names = {item["table"] for item in documents if item.get("table")}
        names |= {item["file_path"] for item in documents}
        return names

    def prompt_rules(self) -> str:
        return (
            "Use search_sql_content when the user asks about specific SQL logic (a filter, a join "
            "condition, a macro, a calculation) inside an ingested file — not for lineage structure "
            "questions, which belong to downstream/upstream/search_tables instead."
        )

    def template(self, result: CapabilityResult) -> str:
        documents = result.extra.get("documents", [])
        return "SQL documents matching the query: " + ", ".join(
            f"{item['file_path']}#{item['statement_order']}" for item in documents
        )


SEARCH_SQL_CONTENT_CAPABILITY = SearchSqlContentCapability()
