"""Dry-run DDL impact simulation against a detached lineage graph."""

from __future__ import annotations

from typing import Literal

from sqlglot import parse as sqlglot_parse
from sqlglot.errors import SqlglotError

from src.config import get_settings
from src.models.schemas import DdlPreviewResult, LineageEdge, StatementPreview, StatementRisk, StatementRiskGroup
from src.services import graph_service, impact_service
from src.services.parser_service import SQLParserService


def _graph_edges(graph) -> list[tuple[str, str, int, LineageEdge]]:
    return [
        (source, target, key, graph_service._attrs_to_edge(source, target, attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
    ]


def _empty_result(parse_error: str) -> DdlPreviewResult:
    return DdlPreviewResult(
        statements=[],
        removed_edges=[],
        orphaned_tables=[],
        unknown_tables=[],
        rename_conflicts=[],
        unsupported_statements=[],
        parse_error=parse_error,
        edges_before=0,
        edges_after=0,
        tables_before=0,
        tables_after=0,
    )


def _outgoing_risks(graph, table: str, *, order: int, change_kind: Literal["drop_table", "rename_table"]):
    """Capture direct downstream risk before a DDL mutation changes this graph."""
    risks = [
        StatementRisk(
            source_table=edge.source_table,
            source_column=edge.source_column,
            target_table=edge.target_table,
            target_column=edge.target_column,
            risk=impact_service.risk_note(edge.transform_type, change_kind),
        )
        for source, target, _, attrs in graph.out_edges(table, keys=True, data=True)
        for edge in [graph_service._attrs_to_edge(source, target, attrs)]
    ]
    return StatementRiskGroup(order=order, table=table, change_kind=change_kind, risks=risks)


def preview(database_id: int, sql: str, dialect: str | None = None) -> DdlPreviewResult:
    """Simulate supported DDL in statement order without mutating the live graph."""
    active_dialect = dialect or get_settings().sql_dialect
    try:
        statements = [statement for statement in sqlglot_parse(sql, read=active_dialect) if statement is not None]
    except (SqlglotError, Exception) as exc:
        return _empty_result(f"sqlglot parse error: {exc}")

    if not statements:
        return _empty_result("sqlglot không tách được câu lệnh nào hợp lệ")

    parser = SQLParserService(default_dialect=active_dialect)
    events, _ = parser.parse_text_events(sql, dialect=active_dialect)
    events_by_order = {event.order: event for event in events}
    working = graph_service.snapshot(database_id)
    before_edges = _graph_edges(working)
    before_in_degree = {str(table): int(in_degree) for table, in_degree in working.in_degree()}
    tables_before = len(working.nodes)
    edges_before = len(before_edges)

    aliases: dict[str, str] = {}
    previews: list[StatementPreview] = []
    unknown_tables: list[str] = []
    rename_conflicts: list[dict[str, str]] = []
    unsupported_statements: list[str] = []
    risk_by_statement: list[StatementRiskGroup] = []

    for order, statement in enumerate(statements):
        event = events_by_order.get(order)
        statement_sql = statement.sql(dialect=active_dialect)[:200]
        if event is None or event.kind not in {"drop", "rename"}:
            previews.append(StatementPreview(order=order, sql=statement_sql, kind="unsupported", status="unsupported"))
            unsupported_statements.append(statement_sql)
            continue

        if event.kind == "drop":
            assert event.table is not None
            if event.table in working:
                risk_by_statement.append(_outgoing_risks(working, event.table, order=order, change_kind="drop_table"))
                graph_service.drop_table(database_id, event.table, graph=working)
                drop_status: Literal["applied", "unknown_table", "unsupported", "rename_conflict"] = "applied"
            else:
                drop_status = "unknown_table"
                unknown_tables.append(event.table)
            previews.append(
                StatementPreview(
                    order=order, sql=statement_sql, kind="drop", table=event.table, status=drop_status
                )
            )
            continue

        assert event.table is not None and event.new_name is not None
        status: Literal["applied", "unknown_table", "unsupported", "rename_conflict"]
        if event.table not in working:
            status = "unknown_table"
            unknown_tables.append(event.table)
        elif event.new_name in working:
            status = "rename_conflict"
            rename_conflicts.append({"table": event.table, "new_name": event.new_name})
        else:
            risk_by_statement.append(_outgoing_risks(working, event.table, order=order, change_kind="rename_table"))
            graph_service.rename_table(database_id, event.table, event.new_name, graph=working)
            aliases = {name: (event.new_name if current == event.table else current) for name, current in aliases.items()}
            aliases[event.table] = event.new_name
            status = "applied"
        previews.append(
            StatementPreview(
                order=order,
                sql=statement_sql,
                kind="rename",
                table=event.table,
                new_name=event.new_name,
                status=status,
            )
        )

    after_edges = _graph_edges(working)
    after_edge_keys = {(source, target, key) for source, target, key, _ in after_edges}
    removed_edges = [
        edge
        for source, target, key, edge in before_edges
        if (aliases.get(source, source), aliases.get(target, target), key) not in after_edge_keys
    ]
    orphaned_tables = sorted(
        aliases[table] if table in aliases else table
        for table, in_degree in before_in_degree.items()
        if in_degree > 0
        and (aliases[table] if table in aliases else table) in working
        and working.in_degree(aliases[table] if table in aliases else table) == 0
    )
    return DdlPreviewResult(
        statements=previews,
        removed_edges=removed_edges,
        orphaned_tables=orphaned_tables,
        unknown_tables=unknown_tables,
        rename_conflicts=rename_conflicts,
        unsupported_statements=unsupported_statements,
        risk_by_statement=risk_by_statement,
        edges_before=edges_before,
        edges_after=len(after_edges),
        tables_before=tables_before,
        tables_after=len(working.nodes),
    )
