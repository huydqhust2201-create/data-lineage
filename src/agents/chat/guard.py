"""Best-effort grounding checks for prose returned by the chat agent."""

from __future__ import annotations

import re
from typing import Any

from src.agents.chat.resolve import normalize

FILE_EXTENSIONS = {"sql", "yml", "yaml", "py", "md", "json", "csv", "txt", "toml", "ini", "cfg", "sh"}
# Chỉ khớp token DẠNG schema.table/table.column (có ít nhất 1 dấu chấm) — cố
# tình bỏ nhánh bare snake_case (vd "orders_backup") từng khớp trước đây:
# nhánh đó chặn nhầm rất nhiều từ vựng kỹ thuật chung hợp lệ trong câu trả lời
# tư vấn/đề xuất (vd "soft_delete", "deprecation_window"), khiến agent trả về
# template cụt lủn thay vì câu trả lời thật cho MỌI câu hỏi dạng "hãy đề
# xuất/giải thích" — không chỉ câu hỏi tra cứu thuần. Đánh đổi đã cân nhắc:
# bỏ lọt tên bảng bịa không có dấu chấm, đổi lấy việc không còn chặn nhầm tư
# vấn hợp lệ trên diện rộng.
TABLE_TOKEN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+",
    re.IGNORECASE,
)


def _fact_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        nested = set().union(*(_fact_keys(item) for item in value.values())) if value else set()
        return set(value) | nested
    if isinstance(value, list):
        return set().union(*(_fact_keys(item) for item in value)) if value else set()
    return set()


def _fact_identifiers(value: Any) -> set[str]:
    """Return identifiers embedded in explicitly trusted fact fields only."""
    if isinstance(value, dict):
        identifiers = {
            normalize(token)
            for expression in (value.get("transform_expression"), value.get("definition_sql"))
            if isinstance(expression, str)
            for token in TABLE_TOKEN.findall(expression)
        }
        nested = set().union(*(_fact_identifiers(item) for item in value.values())) if value else set()
        return identifiers | nested
    if isinstance(value, list):
        return set().union(*(_fact_identifiers(item) for item in value)) if value else set()
    return set()


def unknown_mentions(
    answer: str, facts: dict[str, Any], vocabulary: set[str], question: str = ""
) -> list[str]:
    """Return table-like names not present in this turn's capability vocabulary.

    A name the user already typed in their own question (e.g. a proposed new column name in a
    rename/ADD COLUMN request) is not a hallucination even when no tool result can ground it —
    it was never something the model invented, so it is treated as known too.
    """
    text = answer
    paths = [item.get("evidence_file") for item in facts.get("confirmed", [])]
    paths.extend((item.get("evidence") or {}).get("file_path") for item in facts.get("inferred_pending", []))
    paths.extend(asset.get("defined_in") for asset in facts.get("assets", {}).values())
    for path in sorted((path for path in paths if path), key=len, reverse=True):
        text = text.replace(path, " ")

    known = (
        {normalize(value) for value in vocabulary}
        | {normalize(key) for key in _fact_keys(facts)}
        | _fact_identifiers(facts)
        | {normalize(token) for token in TABLE_TOKEN.findall(question)}
    )
    unknown = []
    for token in TABLE_TOKEN.findall(text):
        suffix = token.rsplit(".", 1)[-1].lower()
        normalized = normalize(token)
        qualified_parts = [normalize(part) for part in token.split(".")]
        if suffix in FILE_EXTENSIONS or normalized in known or (
            len(qualified_parts) > 1 and all(part in known for part in qualified_parts)
        ):
            continue
        if token not in unknown:
            unknown.append(token)
    return unknown
