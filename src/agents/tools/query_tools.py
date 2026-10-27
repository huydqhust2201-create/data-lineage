"""Chat capability for analysing user-supplied SELECT statements."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.agents.chat.resolve import known_tables, normalize
from src.services.parser_service import SQLParserService


class AnalyzeQueryParams(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)
    dialect: str | None = None


def _resolved_table(table: str, database_id: int) -> str | None:
    """Return only an exact graph table match; never bless a query typo."""
    matches = [candidate for candidate in known_tables(database_id) if normalize(candidate) == normalize(table)]
    return matches[0] if len(matches) == 1 else None


class AnalyzeQueryCapability:
    name = "analyze_query"
    description = "Parse a pasted SELECT query and identify its recorded source tables and columns."
    Params = AnalyzeQueryParams

    def run(self, params: AnalyzeQueryParams, database_id: int) -> CapabilityResult:
        parser = SQLParserService()
        events, reason = parser.parse_text_events(params.sql, dialect=params.dialect)
        if reason and reason.startswith("sqlglot parse error"):
            return CapabilityResult(error="sql_parse_failed", extra={"reason": "The query could not be parsed."})

        columns = []
        for event in events:
            for edge in event.edges:
                resolved_table = _resolved_table(edge.source_table, database_id)
                columns.append(
                    {
                        "output_column": edge.target_column,
                        "source_table": resolved_table or edge.source_table,
                        "source_column": edge.source_column,
                        "resolved": resolved_table is not None,
                    }
                )
        extra: dict[str, Any] = {"query_columns": columns}
        if reason:
            extra["note"] = reason
        return CapabilityResult(extra=extra)

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        return {
            value
            for column in result.extra.get("query_columns", [])
            if column["resolved"]
            for value in (column["source_table"], column["source_column"])
            if value is not None
        }

    def prompt_rules(self) -> str:
        return "Use analyze_query when the user pastes a SELECT query and asks where its data comes from."

    def template(self, result: CapabilityResult) -> str:
        return f"Query sources: {len(result.extra.get('query_columns', []))} column dependency(s)."


ANALYZE_QUERY_CAPABILITY = AnalyzeQueryCapability()
