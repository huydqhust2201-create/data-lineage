"""Read breaking-change alerts as grounded chat facts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.agents.chat.base import CapabilityResult
from src.agents.chat.resolve import mentions_identifier
from src.services import graph_service, storage_service


class BreakingChangesParams(BaseModel):
    tables: list[str] | None = None


class BreakingChangesCapability:
    name = "breaking_changes"
    description = (
        "Read rename and drop alerts. For a specific issue, pass the root table and upstream tables returned by traverse."
    )
    Params = BreakingChangesParams

    @staticmethod
    def _repair_guidance(alert: storage_service.BreakingChangeAlertRecord, edges: list[Any]) -> dict:
        """Separate direct SQL references from downstream tables affected transitively."""
        direct_refs: list[dict[str, object]] = []
        transitive_refs: list[str] = []
        seen: set[tuple[str, str | None, str]] = set()
        for downstream in alert.downstream_tables:
            found_direct_ref = False
            for edge in edges:
                evidence = edge.evidence
                raw_sql = evidence.raw_sql if evidence else None
                if edge.target_table != downstream or not raw_sql:
                    continue
                for line_number, line in enumerate(raw_sql.splitlines(), start=1):
                    if not mentions_identifier(line, alert.table_name):
                        continue
                    sql_line = line.strip()
                    identity = (downstream, evidence.file_path, sql_line)
                    if identity not in seen:
                        seen.add(identity)
                        direct_refs.append(
                            {
                                "table": downstream,
                                "file": evidence.file_path,
                                "stored_sql_line": line_number,
                                "sql_line": sql_line,
                            }
                        )
                    found_direct_ref = True
                    break
            if not found_direct_ref:
                transitive_refs.append(downstream)
        return {"direct_refs": direct_refs, "transitive_refs": transitive_refs}

    def run(self, params: BreakingChangesParams, database_id: int) -> CapabilityResult:
        try:
            alerts = storage_service.list_breaking_change_alerts(database_id, include_acknowledged=True)
        except Exception:
            return CapabilityResult(error="breaking_changes_unavailable")
        if params.tables is not None:
            tables = {table.lower() for table in params.tables}
            alerts = [
                alert
                for alert in alerts
                if tables.intersection({alert.table_name.lower(), (alert.new_name or "").lower()})
                or tables.intersection(table.lower() for table in alert.downstream_tables)
            ]
        try:
            edges = graph_service.get_all_edges(database_id)
        except Exception:
            # The alert itself remains useful even if stored graph evidence is unavailable.
            edges = []
        repair_guidance = {alert.id: self._repair_guidance(alert, edges) for alert in alerts}
        return CapabilityResult(
            extra={
                "breaking_changes": alerts,
                "checked_tables": params.tables,
                "breaking_change_repair_guidance": repair_guidance,
            }
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        names: set[str] = set()
        for alert in result.extra.get("breaking_changes", []):
            names.add(alert.table_name)
            if alert.new_name:
                names.add(alert.new_name)
            names.update(alert.downstream_tables)
        return names

    def prompt_rules(self) -> str:
        return (
            "When the user reports something wrong or asks why a table fails, call breaking_changes BEFORE "
            "investigating lineage — an upstream rename or drop is a common cause. Only look elsewhere if it "
            "returns nothing; when it returns nothing, call traverse upstream for the table and column named by "
            "the user before answering. Not for plain lineage questions."
        )

    def template(self, result: CapabilityResult) -> str:
        return f"{len(result.extra.get('breaking_changes', []))} breaking-change alert(s) found."


BREAKING_CHANGES_CAPABILITY = BreakingChangesCapability()
