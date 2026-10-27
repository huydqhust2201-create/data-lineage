"""Chat capabilities backed by the shared impact service."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.chat.base import CapabilityResult, edge_fingerprint, resolve_or_error
from src.agents.chat.resolve import columns_for_table, is_known_column, resolve_column
from src.config import get_settings
from src.models.schemas import LineageEdge
from src.services import graph_service, impact_service
from src.services.impact_service import ChangeKind

# Bảng map rủi ro theo transform_type dùng chung với REST /impact/{table}
# (impact_service.risk_note) — không định nghĩa lại ở đây.


def _risk_by_edge(edges: list[LineageEdge], change_kind: ChangeKind) -> dict[str, str]:
    return {
        edge_fingerprint(edge): impact_service.risk_note(edge.transform_type, change_kind, edge.dependency_kind)
        for edge in edges
    }


_CHANGE_KIND_PROMPT_RULE = (
    "Set change_kind='type' for data-type changes and 'value' for data/content changes. For one column, "
    "use 'drop' or 'rename'; for a whole table/model, use 'drop_table' or 'rename_table'. Use 'add_column' "
    "when a NEW column is added, and 'constraint' when a NOT NULL / primary-key / foreign-key / partition "
    "key changes on an EXISTING column. Omit it for plain dependency questions. State each returned per-edge "
    "risk note next to that edge."
)

_COLUMN_FILTER_NOTE = (
    "Đã lọc bám theo đúng cột này qua nhiều hop; nếu gặp 1 cạnh không rõ cột "
    "(vd SELECT *), từ đó trở đi rơi về mức cả bảng để không bỏ sót ảnh hưởng."
)


def _column_filter_note(resolved_column: str | None) -> str | None:
    return _COLUMN_FILTER_NOTE if resolved_column is not None else None


class AssessChangeParams(BaseModel):
    table: str = Field(..., min_length=1)
    column: str | None = None
    change_kind: ChangeKind


class TraverseParams(BaseModel):
    table: str = Field(..., min_length=1)
    direction: Literal["upstream", "downstream"]
    column: str | None = None
    depth: int | None = Field(default=None, ge=1)


def _error_vocabulary(result: CapabilityResult) -> set[str]:
    if result.error in {"ambiguous", "column_not_found"}:
        return set(result.extra.get("candidates", []))
    if result.error == "table_not_found":
        return set(result.extra.get("suggestions", []))
    return set()


def _result_vocabulary(result: CapabilityResult) -> set[str]:
    tables = _error_vocabulary(result)
    if result.extra.get("resolved_table"):
        tables.add(result.extra["resolved_table"])
    if result.extra.get("resolved_column"):
        tables.add(result.extra["resolved_column"])
    for edge in [*result.confirmed, *result.pending]:
        tables.update(
            name
            for name in (edge.source_table, edge.target_table, edge.source_column, edge.target_column)
            if name is not None
        )
    return tables


def _resolve_column_or_error(database_id: int, table: str, mention: str | None) -> str | CapabilityResult | None:
    column = resolve_column(database_id, table, mention)
    if mention and column is None:
        return CapabilityResult(
            error="column_not_found",
            extra={"mention": mention, "table": table, "candidates": columns_for_table(database_id, table)},
        )
    return column


class TraverseCapability:
    """Traverse confirmed and pending lineage in the requested direction."""

    name = "traverse"
    description = "Traverse confirmed and pending lineage for one table in an upstream or downstream direction."
    Params = TraverseParams

    def run(self, params: TraverseParams, database_id: int) -> CapabilityResult:
        resolved = resolve_or_error(params.table, database_id, direction=params.direction)
        if isinstance(resolved, CapabilityResult) and params.column and is_known_column(database_id, params.column):
            resolved = resolve_or_error(params.column, database_id, direction=params.direction)
        if isinstance(resolved, CapabilityResult):
            return resolved
        column = _resolve_column_or_error(database_id, resolved, params.column)
        if isinstance(column, CapabilityResult):
            return column
        depth = params.depth if params.depth is not None else get_settings().chat_default_traverse_depth
        confirmed, pending = impact_service.query_impact_edges(database_id, resolved, column, params.direction, depth)
        extra: dict[str, Any] = {
            "resolved_table": resolved,
            "resolved_column": column,
            "direction": params.direction,
            "column_filter_note": _column_filter_note(column),
        }
        if params.direction == "upstream":
            extra["hops_by_edge"] = {
                edge_fingerprint(edge): hops for edge, hops in graph_service.get_upstream_with_hops(
                    database_id, resolved, column, depth
                )
            }
        return CapabilityResult(confirmed=confirmed, pending=pending, extra=extra)

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        return _result_vocabulary(result)

    def prompt_rules(self) -> str:
        return (
            "Use for where data comes from, what it feeds into, or how a column is computed. "
            "Use 'upstream' for origins and 'downstream' for dependents. Default depth is 2; "
            "request more for ultimate/raw origins."
        )

    def template(self, result: CapabilityResult) -> str:
        if result.extra["direction"] == "upstream":
            confirmed = ", ".join(edge.source_table for edge in result.confirmed) or "chưa có cạnh nào"
            pending = ", ".join(edge.source_table for edge in result.pending)
            return "Nguồn đã xác nhận: " + confirmed + (". Giả thuyết chưa duyệt: " + pending if pending else "")
        confirmed = ", ".join(edge.target_table for edge in result.confirmed) or "chưa có cạnh nào"
        pending = ", ".join(edge.target_table for edge in result.pending)
        return "Ảnh hưởng đã xác nhận: " + confirmed + (". Giả thuyết chưa duyệt: " + pending if pending else "")


class AssessChangeCapability:
    """Assess downstream risk when a table or column changes."""

    name = "assess_change"
    description = "Assess downstream lineage risk for a specified table or column change."
    Params = AssessChangeParams

    def run(self, params: AssessChangeParams, database_id: int) -> CapabilityResult:
        resolved = resolve_or_error(params.table, database_id, direction="downstream")
        if isinstance(resolved, CapabilityResult):
            return resolved
        column = _resolve_column_or_error(database_id, resolved, params.column)
        if isinstance(column, CapabilityResult):
            return column
        confirmed, pending = impact_service.query_impact_edges(database_id, resolved, column, "downstream")
        return CapabilityResult(
            confirmed=confirmed,
            pending=pending,
            extra={
                "resolved_table": resolved,
                "resolved_column": column,
                "direction": "downstream",
                "column_filter_note": _column_filter_note(column),
                "risk_by_edge": _risk_by_edge([*confirmed, *pending], params.change_kind),
            },
        )

    def vocabulary(self, result: CapabilityResult) -> set[str]:
        return _result_vocabulary(result)

    def prompt_rules(self) -> str:
        return (
            "Use when the user asks what breaks or what is affected if a column or table is changed, renamed, or dropped. "
            + _CHANGE_KIND_PROMPT_RULE
        )

    def template(self, result: CapabilityResult) -> str:
        confirmed = ", ".join(edge.target_table for edge in result.confirmed) or "chưa có cạnh nào"
        pending = ", ".join(edge.target_table for edge in result.pending)
        return "Ảnh hưởng đã xác nhận: " + confirmed + (". Giả thuyết chưa duyệt: " + pending if pending else "")


TRAVERSE_CAPABILITY = TraverseCapability()
ASSESS_CHANGE_CAPABILITY = AssessChangeCapability()
