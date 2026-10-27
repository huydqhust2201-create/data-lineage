"""Semantic table discovery backed by persisted table descriptions."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.agents.chat.resolve import normalize
from src.config import get_settings
from src.services import embedding_service, graph_service, storage_service

logger = logging.getLogger(__name__)


class SearchByDescriptionParams(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int | None = Field(default=None, ge=1)


class SearchByDescriptionCapability:
    name = "search_by_description"
    description = (
        "Find tables by meaning — what data they hold, what they are for — using their stored "
        "descriptions. Use when the question describes data by purpose, topic, or content instead "
        "of naming a table."
    )
    Params = SearchByDescriptionParams

    def run(self, params: SearchByDescriptionParams, database_id: int) -> CapabilityResult:
        settings = get_settings()
        if not settings.description_enabled:
            return CapabilityResult(error="descriptions_disabled")

        try:
            total = storage_service.count_searchable_descriptions(database_id)
        except Exception:
            logger.exception("Semantic description search failed")
            return CapabilityResult(error="search_unavailable")
        if total == 0:
            return CapabilityResult(error="index_empty")

        vectors = embedding_service.embed([params.query])
        if not vectors:
            return CapabilityResult(error="embedding_unavailable")

        limit = min(params.limit or settings.chat_search_limit, settings.chat_search_limit)
        try:
            matches = storage_service.search_descriptions(database_id, vectors[0], limit)
        except Exception:
            logger.exception("Semantic description search failed")
            return CapabilityResult(error="search_unavailable")
        return CapabilityResult(
            extra={
                "tables": [name for name, _, _ in matches[:limit]],
                "truncated": total > limit,
                "total": total,
            }
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        return set(result.extra.get("tables", []))

    def prompt_rules(self) -> str:
        return (
            "Use search_by_description (not search_tables) when the question describes what a table "
            "holds or is for and names no table — e.g. 'which table has the date calendar', "
            "'where is supply cost'. search_tables only matches text inside table names, so it finds "
            "nothing for those questions; try search_by_description before saying no table matches."
        )

    def template(self, result: CapabilityResult) -> str:
        tables = result.extra.get("tables", [])
        return "Tables matching the description: " + ", ".join(tables)


SEARCH_BY_DESCRIPTION_CAPABILITY = SearchByDescriptionCapability()


class SearchColumnByDescriptionParams(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int | None = Field(default=None, ge=1)


class SearchColumnByDescriptionCapability:
    name = "search_column_description"
    description = (
        "Find table.column pairs by meaning using stored column descriptions. Use only when the user describes "
        "a column's purpose or meaning without naming the column; use traverse when a column is named."
    )
    Params = SearchColumnByDescriptionParams

    def run(self, params: SearchColumnByDescriptionParams, database_id: int) -> CapabilityResult:
        settings = get_settings()
        query = normalize(params.query)
        exact = sorted(
            {
                (table, column)
                for edge in graph_service.get_all_edges(database_id)
                for table, column in ((edge.source_table, edge.source_column), (edge.target_table, edge.target_column))
                if column is not None and normalize(column) == query
            }
        )
        if exact:
            try:
                descriptions = storage_service.load_column_descriptions_by_names(
                    database_id, sorted({table for table, _column in exact})
                )
            except Exception:
                logger.exception("Failed to load exact column descriptions")
                descriptions = {}
            return CapabilityResult(
                extra={
                    "columns": [
                        {
                            "table": table,
                            "column": column,
                            "description": description.description if (description := descriptions.get((table, column))) else None,
                        }
                        for table, column in exact
                    ],
                    "truncated": False,
                    "total": len(exact),
                    "match_kind": "exact",
                }
            )
        if not settings.description_enabled:
            return CapabilityResult(error="descriptions_disabled")

        try:
            total = storage_service.count_searchable_column_descriptions(database_id)
        except Exception:
            logger.exception("Semantic column description search failed")
            return CapabilityResult(error="search_unavailable")
        if total == 0:
            return CapabilityResult(error="index_empty")

        vectors = embedding_service.embed([params.query])
        if not vectors:
            return CapabilityResult(error="embedding_unavailable")

        limit = min(params.limit or settings.chat_search_limit, settings.chat_search_limit)
        try:
            matches = storage_service.search_column_descriptions(database_id, vectors[0], limit)
        except Exception:
            logger.exception("Semantic column description search failed")
            return CapabilityResult(error="search_unavailable")
        return CapabilityResult(
            extra={
                "columns": [
                    {"table": table, "column": column, "description": description}
                    for table, column, description, _score in matches[:limit]
                ],
                "truncated": total > limit,
                "total": total,
                "match_kind": "semantic" if matches else "none",
            }
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        matches = result.extra.get("columns", [])
        tables = {item["table"] for item in matches}
        columns = {item["column"] for item in matches}
        return tables | columns

    def prompt_rules(self) -> str:
        return (
            "Use search_column_description only when the user describes a column's purpose or meaning without "
            "naming the column; when a column is named, use traverse. Use search_by_description for tables."
        )

    def template(self, result: CapabilityResult) -> str:
        matches = result.extra.get("columns", [])
        return "Columns matching the description: " + ", ".join(f"{item['table']}.{item['column']}" for item in matches)


SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY = SearchColumnByDescriptionCapability()
