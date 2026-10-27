"""Shared table-name normalization for parser and LLM lineage paths."""

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect

JINJA_MARKERS = ("{{", "{%-", "{%")


def qualified_table_name(table: exp.Table, dialect: str) -> str:
    """Return a dialect-normalized catalog.db.table name from a SQLGlot AST."""
    dial = Dialect.get_or_raise(dialect)
    parts: list[str] = []
    for key in ("catalog", "db", "this"):
        node = table.args.get(key)
        if isinstance(node, exp.Identifier) and node.name:
            parts.append(dial.normalize_identifier(node.copy()).name)
    return ".".join(parts)


def normalize_table_name(name: str, dialect: str) -> str:
    """Normalize an LLM-provided table name without parsing or raising."""
    try:
        dial = Dialect.get_or_raise(dialect)
        parts: list[str] = []
        for raw_part in name.strip().rstrip(";").strip().split("."):
            part = raw_part.strip()
            if not part:
                continue
            quoted = any(marker in part for marker in ('"', "`", "[", "]"))
            identifier = part.strip('"`[]').strip()
            if not identifier:
                continue
            if quoted:
                parts.append(identifier)
            else:
                parts.append(dial.normalize_identifier(exp.Identifier(this=identifier, quoted=False)).name)
        return ".".join(parts)
    except Exception:
        return ""


def should_drop_edge(source_table: str, target_table: str) -> str | None:
    """Return the reason an edge should be dropped, or ``None`` to retain it."""
    if any(marker in source_table or marker in target_table for marker in JINJA_MARKERS):
        return "unresolved Jinja table reference"
    if source_table == target_table:
        return "lineage self-loop"
    return None
