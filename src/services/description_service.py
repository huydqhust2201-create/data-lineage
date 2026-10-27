"""LLM-backed table descriptions and deterministic evidence hashing."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.services import graph_service
from src.services.storage_service import DescriptionNode, NodeRecord

logger = logging.getLogger(__name__)

DESCRIPTION_CONFIDENCE: dict[str, float] = {
    "documented": 0.90,
    "schema_inferred": 0.75,
    "lineage_inferred": 0.50,
    "name_only": 0.30,
}
_DEFAULT_DESCRIPTION_CONFIDENCE: float = 0.30
DESCRIPTION_MAX_CONFIDENCE: float = 0.90


class RawDescription(BaseModel):
    """Structured description returned by the LLM before confidence mapping."""

    description: str
    label: str


class _DescriptionCache:
    """Thread-safe in-memory cache keyed by complete prompt payload hashes."""

    def __init__(self) -> None:
        self._store: dict[str, RawDescription] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> RawDescription | None:
        with self._lock:
            return self._store.get(key)

    def put(self, key: str, value: RawDescription) -> None:
        with self._lock:
            self._store[key] = value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache = _DescriptionCache()


def _load_prompt(filename: str, fallback: str) -> str:
    path = Path(__file__).parent / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Description prompt file not found at %s", path)
        return fallback


_SYSTEM_PROMPT = _load_prompt("_description_prompt_v1.txt", "Return JSON with a cautious table description and a label.")
_COLUMN_SYSTEM_PROMPT = _load_prompt(
    "_column_description_prompt_v1.txt", "Return JSON with a cautious column description and a label."
)


def _neighbour_payload(names: list[str], neighbours: dict[str, NodeRecord]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in sorted(names):
        neighbour = neighbours.get(name)
        if neighbour is None:
            result.append({"name": name, "columns": []})
            continue
        columns = sorted(set(neighbour.columns_produced + neighbour.columns_consumed))
        result.append({"name": name, "columns": columns})
    return result


def build_evidence_payload(node: DescriptionNode, neighbours: dict[str, NodeRecord]) -> dict[str, object]:
    """Build the DB-reconstructible evidence payload; this function never reads files."""
    record = node.record
    return {
        "name": record.current_name,
        "defined_in": record.defined_in,
        "columns_produced": record.columns_produced,
        "columns_consumed": record.columns_consumed,
        "upstream": _neighbour_payload(record.upstream_tables, neighbours),
        "downstream": _neighbour_payload(record.downstream_tables, neighbours),
        "transform_types": record.transform_types,
        "last_modified": node.last_modified.isoformat() if node.last_modified is not None else None,
    }


def build_column_evidence_payload(database_id: int, table: str, column: str) -> dict[str, object]:
    """Build the graph-reconstructible evidence payload for 1 column.

    Chỉ lấy cạnh HOP ĐẦU TIÊN (đi thẳng vào/ra đúng table.column này) từ
    get_upstream/get_downstream — 2 hàm đó giờ đã lan truyền filter cột qua
    nhiều hop (graph_service._traverse), nhưng để mô tả Ý NGHĨA của 1 cột chỉ
    cần biết nó được TÍNH TRỰC TIẾP từ đâu / TRUYỀN TRỰC TIẾP đi đâu, không
    cần cả chuỗi xuyên nhiều bảng. Chỉ dựa trên cạnh đã CONFIRMED (graph_service
    không chứa cạnh pending) — không mô tả cột dựa trên suy luận LLM chưa qua HITL.
    """
    upstream = graph_service.get_upstream(database_id, table, column)
    downstream = graph_service.get_downstream(database_id, table, column)
    produced_by = sorted(
        (
            {"transform_type": edge.transform_type, "from_table": edge.source_table, "from_column": edge.source_column}
            for edge in upstream
            if edge.target_table == table and edge.target_column == column
        ),
        key=lambda item: (item["from_table"], item["from_column"] or "", item["transform_type"]),
    )[:10]
    consumed_by = sorted(
        (
            {"transform_type": edge.transform_type, "to_table": edge.target_table, "to_column": edge.target_column}
            for edge in downstream
            if edge.source_table == table and edge.source_column == column
        ),
        key=lambda item: (item["to_table"], item["to_column"] or "", item["transform_type"]),
    )[:10]
    return {
        "table": table,
        "column": column,
        "produced_by": produced_by,
        "consumed_by": consumed_by,
    }


def evidence_hash(payload: dict[str, object]) -> str:
    """Return a stable SHA-256 digest for DB-reconstructible description evidence."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve_confidence(label: str) -> float:
    """Map an LLM label to the fixed confidence table, safely handling unknown labels."""
    return DESCRIPTION_CONFIDENCE.get(label.strip().lower(), _DEFAULT_DESCRIPTION_CONFIDENCE)


def _get_description_llm() -> Any:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_name,
        api_key=SecretStr(settings.openrouter_api_key),
        base_url=settings.openrouter_base_url,
        temperature=0.0,
    ).with_structured_output(RawDescription)


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _invoke_llm_with_retry(prompt: list[dict[str, str]]) -> object:
    return _get_description_llm().invoke(prompt)


def _build_prompt(payload: dict[str, object], system_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]


def _parse_response(raw: object) -> RawDescription | None:
    if isinstance(raw, RawDescription):
        return raw
    if hasattr(raw, "content"):
        raw = getattr(raw, "content")
    if isinstance(raw, str):
        response_text = raw
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1] if "\n" in response_text else ""
            if response_text.endswith("```"):
                response_text = response_text[:-3]
        try:
            raw = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("Unable to parse table description response: %r", response_text[:500])
            return None
    try:
        return RawDescription.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Unable to validate table description response: %s", exc)
        return None


def _payload_key(payload: dict[str, object], system_prompt: str) -> str:
    # Gộp system_prompt vào key cache — payload bảng và payload cột có shape
    # khác nhau (khoá khác nhau) nên khó đụng độ thật, nhưng gộp cho chắc để
    # 1 prompt không bao giờ trả về description cache của prompt kia.
    return hashlib.sha256(
        json.dumps({"prompt": system_prompt, "payload": payload}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _describe_one(key: str, payload: dict[str, object], system_prompt: str) -> tuple[str, RawDescription | None]:
    try:
        cache_key = _payload_key(payload, system_prompt)
        cached = _cache.get(cache_key)
        if cached is not None:
            return key, cached
        description = _parse_response(_invoke_llm_with_retry(_build_prompt(payload, system_prompt)))
    except RetryError:
        logger.error("Description LLM failed after 3 attempts for %s", key, exc_info=True)
        return key, None
    except Exception:
        logger.error("Description LLM failed for %s", key, exc_info=True)
        return key, None
    if description is not None:
        _cache.put(cache_key, description)
    return key, description


def _describe_many(payloads: dict[str, dict[str, object]], system_prompt: str) -> dict[str, RawDescription]:
    """Describe payloads in parallel, returning only successful LLM responses."""
    if not payloads:
        return {}

    descriptions: dict[str, RawDescription] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(payloads), 8)) as executor:
        futures = [executor.submit(_describe_one, key, payload, system_prompt) for key, payload in payloads.items()]
        for future in concurrent.futures.as_completed(futures):
            try:
                key, description = future.result()
            except Exception:
                logger.exception("Description worker failed")
                continue
            if description is not None:
                descriptions[key] = description
    return descriptions


def describe_tables(payloads: dict[str, dict[str, object]]) -> dict[str, RawDescription]:
    """Describe table payloads in parallel, returning only successful LLM responses."""
    return _describe_many(payloads, _SYSTEM_PROMPT)


def describe_columns(payloads: dict[str, dict[str, object]]) -> dict[str, RawDescription]:
    """Describe column payloads in parallel, returning only successful LLM responses."""
    return _describe_many(payloads, _COLUMN_SYSTEM_PROMPT)


def get_cache() -> _DescriptionCache:
    """Expose the cache for deterministic tests."""
    return _cache
