"""Capability contracts kept independent from LangGraph orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from src.agents.chat.resolve import resolve_table
from src.models.schemas import LineageEdge


@dataclass
class CapabilityResult:
    """Trusted graph facts produced by one chat capability invocation."""

    confirmed: list[LineageEdge] = field(default_factory=list)
    pending: list[LineageEdge] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def resolve_or_error(
    mention: str, database_id: int, *, direction: Literal["upstream", "downstream"] | None = None
) -> str | CapabilityResult:
    """Resolve a trusted table name or return the capability error to expose."""
    resolution = resolve_table(mention, database_id=database_id, direction=direction)
    if resolution.status == "resolved" and resolution.table is not None:
        return resolution.table
    if resolution.status == "ambiguous":
        return CapabilityResult(error="ambiguous", extra={"mention": mention, "candidates": resolution.candidates})
    return CapabilityResult(error="table_not_found", extra={"mention": mention, "suggestions": resolution.suggestions})


def edge_fingerprint(edge: LineageEdge) -> str:
    """Return a stable identity for an edge reconstructed from the graph."""
    evidence_file = edge.evidence.file_path if edge.evidence else None
    return "|".join(
        str(part)
        for part in (
            edge.source_table,
            edge.source_column,
            edge.target_table,
            edge.target_column,
            edge.transform_type,
            edge.source_type,
            round(edge.confidence, 6),
            evidence_file,
        )
    )


class Capability(Protocol):
    """A deterministic graph operation exposed as a tool to the chat LLM."""

    name: str
    description: str
    Params: type[BaseModel]

    def run(self, params: BaseModel, database_id: int) -> CapabilityResult: ...

    def vocabulary(self, result: CapabilityResult) -> set[str]: ...

    def prompt_rules(self) -> str: ...

    def template(self, result: CapabilityResult) -> str: ...
