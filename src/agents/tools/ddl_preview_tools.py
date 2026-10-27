"""Chat capability for previewing DDL lineage impact without making changes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult
from src.models.schemas import DdlPreviewResult
from src.services import ddl_preview_service, graph_service


class PreviewDdlImpactParams(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)
    dialect: str | None = None


def build_prompt_payload(preview: DdlPreviewResult) -> dict:
    return {
        "statements": [
            {
                "order": statement.order,
                "kind": statement.kind,
                "status": statement.status,
                "table": statement.table,
                "new_name": statement.new_name,
            }
            for statement in preview.statements
        ],
        "removed_edges": [
            {
                "source_table": edge.source_table,
                "source_column": edge.source_column,
                "target_table": edge.target_table,
                "target_column": edge.target_column,
            }
            for edge in preview.removed_edges
        ],
        "orphaned_tables": preview.orphaned_tables,
        "unknown_tables": preview.unknown_tables,
        "rename_conflicts": preview.rename_conflicts,
        "unsupported_statements_count": len(preview.unsupported_statements),
        "risk_by_statement": [group.model_dump() for group in preview.risk_by_statement],
        "edges_before": preview.edges_before,
        "edges_after": preview.edges_after,
        "tables_before": preview.tables_before,
        "tables_after": preview.tables_after,
    }


class PreviewDdlImpactCapability:
    name = "preview_ddl_impact"
    description = (
        "Simulate a DDL script (DROP TABLE, ALTER TABLE ... RENAME TO) against the current "
        "lineage graph without changing anything, and report what would break. Use when the "
        "user pastes SQL they are about to deploy and asks what it affects."
    )
    Params = PreviewDdlImpactParams

    def run(self, params: PreviewDdlImpactParams, database_id: int) -> CapabilityResult:
        if not graph_service.get_all_tables(database_id):
            return CapabilityResult(error="graph_is_empty")
        try:
            result = ddl_preview_service.preview(database_id, params.sql, params.dialect)
        except Exception:
            return CapabilityResult(error="preview_unavailable")
        if result.parse_error is not None:
            return CapabilityResult(error="sql_unparsed")
        return CapabilityResult(extra={"ddl_preview": build_prompt_payload(result)})

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        if result.error is not None:
            return set()
        payload = result.extra["ddl_preview"]
        names = set(payload["orphaned_tables"]) | set(payload["unknown_tables"])
        for statement in payload["statements"]:
            names |= {statement["table"], statement["new_name"]} - {None}
        for edge in payload["removed_edges"]:
            names |= {
                edge["source_table"],
                edge["target_table"],
                edge["source_column"],
                edge["target_column"],
            } - {None}
            if edge["source_column"] is not None:
                names.add(f"{edge['source_table']}.{edge['source_column']}")
            if edge["target_column"] is not None:
                names.add(f"{edge['target_table']}.{edge['target_column']}")
        for group in payload["risk_by_statement"]:
            for risk in group["risks"]:
                names |= {
                    risk["source_table"],
                    risk["target_table"],
                    risk["source_column"],
                    risk["target_column"],
                } - {None}
                if risk["source_column"] is not None:
                    names.add(f"{risk['source_table']}.{risk['source_column']}")
                if risk["target_column"] is not None:
                    names.add(f"{risk['target_table']}.{risk['target_column']}")
        return names

    def prompt_rules(self) -> str:
        return (
            "Use preview_ddl_impact when the user pastes SQL they are about to deploy and asks what "
            "it affects; do not guess DDL impact from table names."
        )

    def template(self, result: CapabilityResult) -> str:
        preview = result.extra.get("ddl_preview", {})
        return f"DDL preview: {len(preview.get('removed_edges', []))} lineage edges would be removed."


PREVIEW_DDL_IMPACT_CAPABILITY = PreviewDdlImpactCapability()
