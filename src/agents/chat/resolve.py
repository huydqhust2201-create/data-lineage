"""Deterministic table resolution and clarification matching."""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Literal

from pydantic import BaseModel, Field

from src.services import graph_service, review_service

_MAX_SELECTION_TOKENS = 4
_CONFIRMATION_REPLIES = {
    "ừ", "u", "uh", "đúng", "dung", "đúng rồi", "dung roi", "có", "co", "yes", "y", "ok", "oke", "okay", "phải", "phai",
}


# Bien mot dinh danh: ky tu sat hai ben khong duoc thuoc [A-Za-z0-9_.]. Dung chung cho
# ca ba cho can "khop tron ten bang/cot": viet lai cau hoi khi resume (chat_service),
# tu go needs_selection (query_nodes), va linkify o frontend (ban TypeScript tuong duong
# trong frontend/src/utils/linkifyEntities.ts - hai ban phai dong y tren cung bo ca test).
_IDENTIFIER_BOUNDARY = "A-Za-z0-9_."


def _identifier_pattern(name: str) -> str:
    return rf"(?<![{_IDENTIFIER_BOUNDARY}]){re.escape(name)}(?![{_IDENTIFIER_BOUNDARY}])"


def mentions_identifier(text: str, name: str) -> bool:
    """Whether ``name`` occurs in ``text`` as a complete, case-insensitive identifier."""
    if not name:
        return False
    return bool(re.search(_identifier_pattern(name), text, re.IGNORECASE))


def question_with_choice(question: str, mention: str, chosen: str) -> str:
    """Replace a clarified table mention without touching longer identifiers."""
    if not mention:
        return question
    return re.sub(_identifier_pattern(mention), chosen, question, flags=re.IGNORECASE)


class TableResolution(BaseModel):
    """The result of matching one user mention against trusted table names."""

    status: Literal["resolved", "ambiguous", "not_found"]
    table: str | None = None
    candidates: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


def normalize(value: str) -> str:
    """Normalize a table mention without changing its schema semantics."""
    return value.strip().strip('"`[]').lower()


def _last(value: str) -> str:
    return normalize(value).split(".")[-1]


def known_tables(database_id: int) -> list[str]:
    """Return confirmed tables plus both endpoints of pending HITL edges."""
    values = set(graph_service.get_all_tables(database_id))
    for edge in review_service.list_pending(database_id):
        values.update((edge.source_table, edge.target_table))
    return sorted(values)


def _all_edges(database_id: int):
    """Return every edge that can expose a table or column to chat."""
    return [*graph_service.get_all_edges(database_id), *review_service.list_pending(database_id)]


def columns_for_table(database_id: int, table: str) -> list[str]:
    """List actual column names recorded for one table, including pending edges."""
    columns = {
        column
        for edge in _all_edges(database_id)
        for edge_table, column in (
            (edge.source_table, edge.source_column),
            (edge.target_table, edge.target_column),
        )
        if edge_table == table and column
    }
    return sorted(columns, key=normalize)


def is_known_column(database_id: int, mention: str) -> bool:
    """Whether a name is recorded as a column anywhere in this database graph."""
    normalized = normalize(mention)
    return any(
        column and normalize(column) == normalized
        for edge in _all_edges(database_id)
        for column in (edge.source_column, edge.target_column)
    )


def resolve_column(database_id: int, table: str, mention: str | None) -> str | None:
    """Resolve one real column on a resolved table, or leave the filter unset."""
    if not mention:
        return None
    for edge in _all_edges(database_id):
        if edge.source_table == table and edge.source_column and normalize(edge.source_column) == normalize(mention):
            return edge.source_column
        if edge.target_table == table and edge.target_column and normalize(edge.target_column) == normalize(mention):
            return edge.target_column
    return None


def resolve_table(
    mention: str | None,
    candidates: list[str] | None = None,
    database_id: int | None = None,
    *,
    direction: Literal["upstream", "downstream"] | None = None,
) -> TableResolution:
    """Resolve exact names before progressively looser schema-aware matches."""
    if not mention:
        return TableResolution(status="not_found")
    if candidates is not None:
        options = candidates
    elif database_id is not None:
        options = known_tables(database_id)
    else:
        raise ValueError("database_id is required when resolving against known tables")
    for matcher in (
        lambda candidate: normalize(mention) == normalize(candidate),
        lambda candidate: normalize(mention) == _last(candidate),
        lambda candidate: _last(mention) == _last(candidate),
    ):
        matches = [candidate for candidate in options if matcher(candidate)]
        if len(matches) == 1:
            return TableResolution(status="resolved", table=matches[0])
        if len(matches) > 1:
            return TableResolution(status="ambiguous", candidates=matches)
    if candidates is None and database_id is not None:
        normalized_mention = normalize(mention)
        edges = _all_edges(database_id)
        column_tables = {
            table
            for edge in edges
            for table, column in (
                (edge.source_table, edge.source_column),
                (edge.target_table, edge.target_column),
            )
            if column and normalize(column) == normalized_mention
        }
        if len(column_tables) == 1:
            return TableResolution(status="resolved", table=next(iter(column_tables)))
        if len(column_tables) > 1:
            if direction is None:
                return TableResolution(status="ambiguous", candidates=sorted(column_tables))
            incoming: set[str] = set()
            outgoing: set[str] = set()
            for edge in edges:
                if (
                    edge.source_table in column_tables
                    and edge.target_table in column_tables
                    and edge.source_column
                    and edge.target_column
                    and normalize(edge.source_column) == normalized_mention
                    and normalize(edge.target_column) == normalized_mention
                ):
                    outgoing.add(edge.source_table)
                    incoming.add(edge.target_table)
            entries = column_tables - (incoming if direction == "downstream" else outgoing)
            # A cycle has no directional entry. Keep every real candidate rather
            # than producing an unanswerable empty clarification.
            entries = entries or column_tables
            if len(entries) == 1:
                return TableResolution(status="resolved", table=next(iter(entries)))
            return TableResolution(status="ambiguous", candidates=sorted(entries))
    normalized = [normalize(candidate) for candidate in options]
    fuzzy_matches = set(get_close_matches(normalize(mention), normalized, n=5, cutoff=0.6))
    return TableResolution(
        status="not_found", suggestions=[candidate for candidate in options if normalize(candidate) in fuzzy_matches]
    )


def match_clarification(reply: str, candidates: list[str]) -> str | None:
    """Match a clarification reply only to a candidate that was shown to the user."""
    stripped = reply.strip()
    if not stripped:
        return None
    if stripped.isdigit() and 1 <= int(stripped) <= len(candidates):
        return candidates[int(stripped) - 1]
    exact = [candidate for candidate in candidates if normalize(reply) == normalize(candidate)]
    if len(exact) == 1:
        return exact[0]
    if len(stripped.split()) <= _MAX_SELECTION_TOKENS:
        resolved = resolve_table(reply, candidates)
        if resolved.status == "resolved":
            return resolved.table
        contained = [candidate for candidate in candidates if normalize(candidate) in normalize(reply)]
        if len(contained) == 1:
            return contained[0]
    if len(candidates) == 1 and normalize(reply) in _CONFIRMATION_REPLIES:
        return candidates[0]
    return None
