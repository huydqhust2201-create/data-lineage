"""LLM fallback extraction for SQL/dbt lineage, including column mappings — v4.

Cải tiến so với llm_extraction_service.py gốc:
  1. **File-Based Cache (SHA-256)**: Băm nội dung file trước khi gọi LLM.
     Nếu mã băm đã tồn tại trong cache VÀ kết quả parse trước đó không lỗi
     → trả luôn kết quả cũ, tiết kiệm chi phí API.

  2. **Retry & Circuit Breaker (tenacity)**: Bọc hàm gọi LLM bằng
     `tenacity.retry` với `wait_exponential` (1→2→4s) và tối đa 3 lần.
     Nếu vẫn lỗi → gán trạng thái `system_error`, ghi log, trả kết quả rỗng
     — KHÔNG crash pipeline.

  3. **Prompt v4** từ file `_llm_prompt_v4.txt`: bổ sung `resolution_method`,
     thêm transform_type `union`, few-shot examples cải tiến.

Quoted identifiers containing literal dots are not supported by the lightweight
normalizer below; the MVP fixtures do not contain that SQL dialect edge case.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src import metrics
from src.config import get_settings
from src.models.schemas import LineageEdge, LineageEvidence
from src.services.naming import normalize_table_name, should_drop_edge

logger = logging.getLogger(__name__)

# Safety invariant: an LLM-derived edge must never equal parser confidence.
LLM_MAX_CONFIDENCE: float = 0.95
PROMPT_VERSION = "v4"
VALID_TRANSFORM_TYPES = {"direct", "conditional", "aggregation", "join", "union", "unknown"}
VALID_DEPENDENCY_KINDS = {"output", "filter", "join_key", "group_key", "window_partition", "window_order"}
_MISSING_REASONING_PLACEHOLDER = "⚠ LLM không cung cấp giải thích cho cạnh này (vi phạm chỉ thị prompt)"
_MISSING_REASONING_DETAIL_PLACEHOLDER = (
    "⚠ LLM không cung cấp giải thích chi tiết cho cạnh này (vi phạm chỉ thị prompt)"
)

# Schema contract LineageEdge chỉ cho phép 4 giá trị transform_type.
# "union" chưa có trong schema → map sang giá trị tương thích.
_TRANSFORM_TYPE_COMPAT: dict[str, str] = {
    "union": "unknown",
}

# ---------------------------------------------------------------------------
# Prompt v4 — đọc từ file _llm_prompt_v4.txt cùng thư mục
# ---------------------------------------------------------------------------
_PROMPT_V4_PATH = Path(__file__).parent / "_llm_prompt_v4.txt"
try:
    _SYSTEM_PROMPT = _PROMPT_V4_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    logger.warning(
        "Prompt v4 file not found at %s, falling back to inline prompt.",
        _PROMPT_V4_PATH,
    )
    _SYSTEM_PROMPT = (
        "You extract table-level data-lineage edges from SQL that a conventional "
        "parser rejected. Return JSON with 'edges' and 'unresolved' arrays."
    )

_USER_TEMPLATE = """File name: {file_name}
SQL dialect: {dialect}

```sql
{sql_text}
```"""

# ---------------------------------------------------------------------------
# Confidence mapping: resolution_method → numeric score (prompt v2 delegates
# confidence scoring to the calling code).
# ---------------------------------------------------------------------------
RESOLUTION_CONFIDENCE: dict[str, float] = {
    "static": 0.90,
    "ref_source": 0.70,
    "branch": 0.50,
    "dynamic": 0.40,
    "macro": 0.35,
    "speculative": 0.25,
}
_DEFAULT_RESOLUTION_CONFIDENCE: float = 0.50


# ═══════════════════════════════════════════════════════════════════════════════
#  Đề xuất 1 — File-Based Cache (SHA-256)
# ═══════════════════════════════════════════════════════════════════════════════


class _ExtractionCache:
    """Thread-safe in-memory cache keyed by SHA-256.

    Dễ dàng swap sang Redis / Postgres bằng cách override `get` / `put`.
    """

    def __init__(self) -> None:
        self._store: dict[str, ExtractionResponse] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(sql_text: str, file_name: str, dialect: str) -> str:
        """SHA-256 hash of (content + file_name + dialect)."""
        payload = f"{sql_text}\x00{file_name}\x00{dialect}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> ExtractionResponse | None:
        with self._lock:
            result = self._store.get(key)
            if result is not None:
                self._hits += 1
            else:
                self._misses += 1
            return result

    def put(self, key: str, value: ExtractionResponse) -> None:
        with self._lock:
            self._store[key] = value

    def clear(self) -> None:
        """Xoá toàn bộ cache (hữu ích trong test)."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._store),
            }


# Singleton cache — module-level, reset được qua clear() hoặc trong test.
_cache = _ExtractionCache()


class _UsageStats:
    """Thread-safe, tích luỹ token usage thật từ response_metadata của
    AIMessage — chỉ có được từ khi _get_extraction_llm() bật include_raw=True
    (trước đó with_structured_output() không kèm raw, không có cách nào lấy
    token usage). Dùng cho eval/run_performance_benchmark.py tính chi phí
    thật, không đoán/bịa số."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self._calls += 1
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens

    def clear(self) -> None:
        with self._lock:
            self._calls = 0
            self._prompt_tokens = 0
            self._completion_tokens = 0

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "calls": self._calls,
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            }


_usage_stats = _UsageStats()


def get_usage_stats() -> dict[str, int]:
    """Token usage thật tích luỹ từ các lần gọi extract_raw() kể từ lần
    clear_usage_stats() gần nhất (hoặc từ lúc process khởi động)."""
    return _usage_stats.stats


def clear_usage_stats() -> None:
    """Reset bộ đếm — dùng đầu 1 lượt benchmark để đo riêng lượt đó."""
    _usage_stats.clear()


def _record_usage_from_message(message: Any) -> None:
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and "input_tokens" in usage:
        _usage_stats.record(int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
        return
    metadata = getattr(message, "response_metadata", None)
    token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if isinstance(token_usage, dict):
        _usage_stats.record(int(token_usage.get("prompt_tokens", 0)), int(token_usage.get("completion_tokens", 0)))


# ═══════════════════════════════════════════════════════════════════════════════
#  Pydantic models
# ═══════════════════════════════════════════════════════════════════════════════


class RawEdge(BaseModel):
    """An LLM claim before normalization and contract enforcement.

    v2 thêm `resolution_method` — LLM trả tín hiệu dạng string thay vì số;
    code sẽ map sang numeric confidence.
    """

    source_table: str
    source_column: str | None = None
    target_table: str
    target_column: str | None = None
    # Control lineage: cột nguồn không vào output nào nhưng quyết định hàng nào
    # xuất hiện (WHERE/JOIN/GROUP BY/OVER). Cạnh control có target_column=None.
    dependency_kind: str = "output"
    transform_type: str = "unknown"
    confidence: float = 0.0
    resolution_method: str | None = None
    # Optional ở schema (không chặn edge hợp lệ khác nếu model bỏ sót 1 field),
    # nhưng _convert_edges gắn placeholder cảnh báo nếu None/rỗng — reasoning
    # không bao giờ đến tay reviewer dưới dạng trống, dù prompt có bị lờ đi.
    reasoning: str | None = None
    # Giải thích dài hơn, hiển thị khi user bấm "Chi tiết" — cùng cơ chế
    # placeholder như `reasoning` nếu model bỏ sót.
    reasoning_detail: str | None = None
    matched_text: str | None = None
    transform_expression: str | None = None


class ExtractionResponse(BaseModel):
    edges: list[RawEdge] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM client + retry (Đề xuất 2)
# ═══════════════════════════════════════════════════════════════════════════════


def _get_extraction_llm() -> Any:
    """Create a deterministic structured-output client for extraction.

    include_raw=True để giữ lại AIMessage gốc (response_metadata/usage_metadata
    có token usage thật, dùng cho get_usage_stats()) — .invoke() trả về dict
    {"raw": AIMessage, "parsed": ExtractionResponse | None, "parsing_error": ...}
    thay vì thẳng ExtractionResponse. _parse_response() xử lý cả 2 hình dạng.
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.0,
    ).with_structured_output(ExtractionResponse, include_raw=True)


@retry(
    retry=retry_if_exception_type((Exception,)),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _invoke_llm_with_retry(prompt: list[dict[str, str]]) -> object:
    """Gọi LLM API với retry exponential backoff (1s → 2s → 4s), tối đa 3 lần.

    Nếu sau 3 lần vẫn fail, tenacity raise `RetryError` (reraise=False) —
    caller bắt RetryError để xử lý graceful, không crash pipeline.
    """
    metrics.record_llm_call("extraction")
    return _get_extraction_llm().invoke(prompt)


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompt builder & response parser
# ═══════════════════════════════════════════════════════════════════════════════


def _build_prompt(
    sql_text: str,
    file_name: str,
    dialect: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                sql_text=sql_text,
                file_name=file_name,
                dialect=dialect,
            ),
        },
    ]


def _parse_response(raw: object) -> ExtractionResponse:
    """Convert supported structured or JSON responses.

    Với include_raw=True (xem _get_extraction_llm), `raw` thường là dict
    {"raw": AIMessage, "parsed": ExtractionResponse | None, ...} — ưu tiên
    "parsed" nếu LangChain tự parse được, fallback về "raw" (AIMessage thô,
    xử lý qua đúng nhánh .content/JSON bên dưới như trước) nếu "parsed" là
    None. Vẫn nhận thẳng ExtractionResponse (test cũ mock _get_extraction_llm
    trả thẳng giá trị này) để không phá vỡ test hiện có.
    """
    if isinstance(raw, dict) and "parsed" in raw:
        parsed = raw.get("parsed")
        if isinstance(parsed, ExtractionResponse):
            return parsed
        raw = raw.get("raw", raw)

    if isinstance(raw, ExtractionResponse):
        return raw

    payload: object = raw
    if isinstance(raw, str):
        payload = raw
    elif hasattr(raw, "content"):
        payload = getattr(raw, "content")

    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            if text.endswith("```"):
                text = text[:-3]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            logger.warning("Unable to parse LLM response: %s", repr(raw)[:500])
            return ExtractionResponse()
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Unable to parse LLM response: %s", repr(raw)[:500])
            return ExtractionResponse()

    if not isinstance(payload, dict):
        logger.warning("Unable to parse LLM response: %s", repr(raw)[:500])
        return ExtractionResponse()

    unresolved = payload.get("unresolved") or []
    if not isinstance(unresolved, list) or not all(isinstance(item, str) for item in unresolved):
        logger.warning("Ignoring malformed 'unresolved' field: %r", unresolved)
        unresolved = []

    edges: list[RawEdge] = []
    raw_edges = payload.get("edges") or []
    if not isinstance(raw_edges, list):
        logger.warning("Unable to parse LLM response: %s", repr(raw)[:500])
        return ExtractionResponse()
    for index, item in enumerate(raw_edges):
        try:
            edges.append(RawEdge.model_validate(item))
        except ValidationError as exc:
            logger.warning("Dropping malformed edge %d: %s", index, exc)
    return ExtractionResponse(edges=edges, unresolved=unresolved)


# ═══════════════════════════════════════════════════════════════════════════════
#  Normalization & conversion
# ═══════════════════════════════════════════════════════════════════════════════


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _check_citation(matched_text: str | None, sql_text: str | None) -> bool | None:
    """Kiểm chứng matched_text có thực sự tồn tại trong file gốc không.

    None = không áp dụng (LLM không trích dẫn gì). False = matched_text
    không tìm thấy trong sql_text — dấu hiệu LLM có thể đã bịa trích dẫn,
    đáng ưu tiên xem xét kỹ hơn khi duyệt HITL."""
    if not matched_text:
        return None
    if not sql_text:
        return False
    if matched_text in sql_text:
        return True
    # Nới lỏng 1 bước cho khác biệt khoảng trắng/xuống dòng LLM có thể tự ý
    # đổi khi trích dẫn, nhưng vẫn giữ strict substring match làm ưu tiên.
    return _normalize_whitespace(matched_text) in _normalize_whitespace(sql_text)


def _resolve_confidence(raw: RawEdge) -> float:
    """Map resolution_method → numeric confidence.

    Nếu LLM trả `resolution_method`, ưu tiên map từ đó (prompt v2).
    Nếu không có → dùng confidence số mà LLM trả (backward compat v1).
    """
    if raw.resolution_method:
        method = raw.resolution_method.strip().lower()
        return RESOLUTION_CONFIDENCE.get(method, _DEFAULT_RESOLUTION_CONFIDENCE)
    return raw.confidence


def _normalize_column_name(column: str | None) -> str | None:
    """Normalize an optional LLM column name to the parser's bare-name contract."""
    if column is None:
        return None
    normalized = column.strip()
    if not normalized:
        return None
    return normalized.rsplit(".", 1)[-1].strip() or None


def _convert_edges(
    response: ExtractionResponse,
    file_name: str = "<inline>",
    *,
    dialect: str,
    file_path: str | None = None,
    raw_sql: str | None = None,
    fallback_reason: str | None = None,
) -> tuple[list[LineageEdge], int]:
    deduplicated: dict[tuple[str, str | None, str, str | None, str], LineageEdge] = {}
    dropped = 0
    for raw in response.edges:
        try:
            drop_reason = should_drop_edge(raw.source_table, raw.target_table)
            if drop_reason is not None:
                logger.debug(
                    "Dropping LLM edge in %s (%s): %s -> %s",
                    file_name,
                    drop_reason,
                    raw.source_table,
                    raw.target_table,
                )
                dropped += 1
                continue

            source_table = normalize_table_name(raw.source_table, dialect)
            target_table = normalize_table_name(raw.target_table, dialect)
            if not source_table or not target_table:
                logger.debug("Dropping edge with an empty table name in %s", file_name)
                dropped += 1
                continue

            drop_reason = should_drop_edge(source_table, target_table)
            if drop_reason is not None:
                logger.debug(
                    "Dropping LLM edge in %s (%s): %s -> %s",
                    file_name,
                    drop_reason,
                    source_table,
                    target_table,
                )
                dropped += 1
                continue

        except Exception as exc:
            logger.debug("Dropping malformed LLM edge in %s: %s", file_name, exc)
            dropped += 1
            continue

        transform_type = raw.transform_type.strip().lower()
        if transform_type not in VALID_TRANSFORM_TYPES:
            transform_type = "unknown"
        # Map v2 transform types → schema contract.
        transform_type = _TRANSFORM_TYPE_COMPAT.get(transform_type, transform_type)
        source_column = _normalize_column_name(raw.source_column)
        target_column = _normalize_column_name(raw.target_column)
        transform_expression = raw.transform_expression.strip() if raw.transform_expression and raw.transform_expression.strip() else None
        if source_column is None and target_column is None:
            transform_expression = None
        dependency_kind = (raw.dependency_kind or "output").strip().lower()
        if dependency_kind not in VALID_DEPENDENCY_KINDS:
            dependency_kind = "output"
        if dependency_kind != "output":
            # Cạnh control lineage không ánh xạ vào 1 cột output cụ thể.
            target_column = None

        # v2: map resolution_method → numeric confidence
        confidence = _resolve_confidence(raw)

        reasoning = raw.reasoning.strip() if raw.reasoning and raw.reasoning.strip() else None
        if reasoning is None:
            logger.warning("LLM edge %s->%s missing reasoning despite prompt instruction", source_table, target_table)
            reasoning = _MISSING_REASONING_PLACEHOLDER
        reasoning_detail = (
            raw.reasoning_detail.strip() if raw.reasoning_detail and raw.reasoning_detail.strip() else None
        )
        if reasoning_detail is None:
            logger.warning(
                "LLM edge %s->%s missing reasoning_detail despite prompt instruction", source_table, target_table
            )
            reasoning_detail = _MISSING_REASONING_DETAIL_PLACEHOLDER
        citation_checks = [
            _check_citation(citation, raw_sql)
            for citation in (raw.matched_text, transform_expression)
            if citation
        ]
        citation_verified = None if not citation_checks else all(check is True for check in citation_checks)
        if citation_verified is False:
            logger.warning(
                "LLM edge %s->%s cites text not found in source — possible hallucination",
                source_table,
                target_table,
            )

        resolution_method = raw.resolution_method.strip().lower() if raw.resolution_method else None
        evidence = LineageEvidence(
            file_path=file_path,
            raw_sql=raw_sql,
            reasoning=reasoning,
            reasoning_detail=reasoning_detail,
            fallback_reason=fallback_reason,
            resolution_method=resolution_method or None,
            matched_text=raw.matched_text,
            citation_verified=citation_verified,
            transform_expression=transform_expression,
        )
        edge = LineageEdge(
            source_table=source_table,
            source_column=source_column,
            target_table=target_table,
            target_column=target_column,
            dependency_kind=dependency_kind,  # type: ignore[arg-type]
            transform_type=transform_type,  # type: ignore[arg-type]
            confidence=min(max(confidence, 0.0), LLM_MAX_CONFIDENCE),
            source_type="llm",
            evidence=evidence,
        )
        key = (source_table, source_column, target_table, target_column, transform_type, dependency_kind)
        if key not in deduplicated or edge.confidence > deduplicated[key].confidence:
            deduplicated[key] = edge
    return [
        deduplicated[key]
        for key in sorted(
            deduplicated, key=lambda item: (item[0], item[1] or "", item[2], item[3] or "", item[4], item[5])
        )
    ], dropped


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════


def to_lineage_edges(
    response: ExtractionResponse,
    file_name: str = "",
    *,
    dialect: str | None = None,
    file_path: str | None = None,
    raw_sql: str | None = None,
    fallback_reason: str | None = None,
) -> list[LineageEdge]:
    """Map raw LLM claims into normalized shared lineage edges (no I/O)."""
    edges, _ = _convert_edges(
        response,
        file_name,
        dialect=dialect or get_settings().sql_dialect,
        file_path=file_path,
        raw_sql=raw_sql,
        fallback_reason=fallback_reason,
    )
    return edges


def extract_raw(
    sql_text: str,
    file_name: str = "<inline>",
    dialect: str | None = None,
) -> ExtractionResponse:
    """Call LLM and return validated, pre-normalization response.

    v2 improvements:
    - SHA-256 cache check before calling API.
    - Retry up to 3 times with exponential backoff.
    - Log `system_error` on complete failure.
    """
    if not sql_text.strip():
        logger.info("LLM extraction skipped for %s: empty input", file_name)
        return ExtractionResponse()

    selected_dialect = dialect or get_settings().sql_dialect
    prompt = _build_prompt(sql_text, file_name, selected_dialect)
    logger.debug("LLM extraction prompt for %s: %s", file_name, prompt)

    # ── Đề xuất 1: kiểm tra cache ──────────────────────────────────────
    cache_key = _cache.make_key(sql_text, file_name, selected_dialect)
    cached = _cache.get(cache_key)
    if cached is not None:
        logger.info(
            "LLM extraction cache HIT for %s (hash=%s…), returning cached result (%d edges)",
            file_name,
            cache_key[:12],
            len(cached.edges),
        )
        return cached

    # ── Đề xuất 2: gọi LLM với retry + circuit breaker ────────────────
    try:
        raw = _invoke_llm_with_retry(prompt)
    except RetryError as retry_err:
        last_exc = retry_err.last_attempt.exception() if retry_err.last_attempt else retry_err
        logger.error(
            "LLM extraction SYSTEM_ERROR for %s after 3 retries: %s. File marked as system_error and skipped.",
            file_name,
            last_exc,
        )
        return ExtractionResponse()
    except Exception:
        logger.exception(
            "LLM extraction failed for %s (non-retryable)",
            file_name,
        )
        return ExtractionResponse()

    logger.debug("LLM extraction raw response for %s: %s", file_name, raw)
    if isinstance(raw, dict) and "raw" in raw:
        _record_usage_from_message(raw["raw"])
    result = _parse_response(raw)

    # ── Đề xuất 1: lưu vào cache ──────────────────────────────────────
    _cache.put(cache_key, result)
    logger.debug(
        "LLM extraction cached for %s (hash=%s…, %d edges). Stats: %s",
        file_name,
        cache_key[:12],
        len(result.edges),
        _cache.stats,
    )
    return result


def extract_edges(
    sql_text: str,
    file_name: str = "<inline>",
    dialect: str | None = None,
    *,
    file_path: str | None = None,
    fallback_reason: str | None = None,
) -> list[LineageEdge]:
    """Extract normalized lineage edges, returning [] on LLM failures.

    `file_path`/`fallback_reason` chỉ ảnh hưởng evidence gắn vào edge,
    không ảnh hưởng nội dung prompt gửi LLM (vẫn dùng `file_name`).
    """
    if not sql_text.strip():
        extract_raw(sql_text, file_name, dialect)
        return []
    response = extract_raw(sql_text, file_name, dialect)
    selected_dialect = dialect or get_settings().sql_dialect
    edges, dropped = _convert_edges(
        response,
        file_name,
        dialect=selected_dialect,
        file_path=file_path or file_name,
        raw_sql=sql_text,
        fallback_reason=fallback_reason,
    )
    logger.info(
        "LLM extraction file=%s chars=%d edges=%d unresolved=%d dropped=%d",
        file_name,
        len(sql_text),
        len(edges),
        len(response.unresolved),
        dropped,
    )
    return edges


def extract_edges_from_file(
    file_path: str,
    dialect: str | None = None,
    *,
    fallback_reason: str | None = None,
) -> list[LineageEdge]:
    """Read a UTF-8 SQL/dbt file and extract its lineage edges."""
    path = Path(file_path)
    return extract_edges(
        path.read_text(encoding="utf-8"),
        path.stem,
        dialect,
        file_path=file_path,
        fallback_reason=fallback_reason,
    )


def extract_edges_from_files(
    file_paths: list[str],
    dialect: str | None = None,
    *,
    fallback_reasons: dict[str, str] | None = None,
) -> dict[str, list[LineageEdge]]:
    """Extract each file independently.

    v2: mỗi file lỗi được ghi system_error riêng — pipeline tiếp tục.
    Chạy song song bằng ThreadPoolExecutor.
    """
    results: dict[str, list[LineageEdge]] = {}
    if not file_paths:
        return results

    def _extract_single(fp: str) -> tuple[str, list[LineageEdge]]:
        try:
            reason = (fallback_reasons or {}).get(fp)
            edges = extract_edges_from_file(
                fp,
                dialect,
                fallback_reason=reason,
            )
            return fp, edges
        except OSError:
            logger.exception("Unable to read SQL file %s", fp)
            return fp, []
        except Exception as e:
            logger.exception("Failed to extract edges from file %s: %s", fp, e)
            return fp, []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(file_paths), 8)) as executor:
        future_to_fp = {executor.submit(_extract_single, fp): fp for fp in file_paths}
        for future in concurrent.futures.as_completed(future_to_fp):
            fp = future_to_fp[future]
            try:
                fp_res, edges = future.result()
                results[fp_res] = edges
            except Exception as e:
                logger.exception("Thread pool execution failed for %s: %s", fp, e)
                results[fp] = []

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Utility — cho test & debug
# ═══════════════════════════════════════════════════════════════════════════════


def get_cache() -> _ExtractionCache:
    """Trả về singleton cache (dùng trong test để inspect/clear)."""
    return _cache
