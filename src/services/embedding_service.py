"""Client for the local Text Embeddings Inference (TEI) service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import get_settings

logger = logging.getLogger(__name__)


def is_reachable() -> bool:
    """Kiểm tra nhanh TEI container còn sống — dùng cho health check (GET
    /status), chỉ gọi khi description_enabled=True. Timeout ngắn, không retry
    (health check phải nhanh, không phải embed request thật)."""
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.embedding_url.rstrip('/')}/health", timeout=1.0)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def _post_embed(payload: dict[str, list[str]]) -> Any:
    """POST an embedding request to TEI.

    Kept separate so callers can test the client without a live TEI container.
    """
    settings = get_settings()
    response = httpx.post(
        f"{settings.embedding_url.rstrip('/')}/embed",
        json=payload,
        timeout=settings.embedding_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _post_embed_with_retry(payload: dict[str, list[str]]) -> Any:
    return _post_embed(payload)


def _valid_embeddings(raw: Any, expected_count: int, expected_dim: int) -> list[list[float]] | None:
    if not isinstance(raw, list) or len(raw) != expected_count:
        logger.error(
            "TEI returned %s vectors for %s inputs", len(raw) if isinstance(raw, list) else "invalid", expected_count
        )
        return None

    embeddings: list[list[float]] = []
    for vector in raw:
        if not isinstance(vector, list) or len(vector) != expected_dim:
            logger.error("TEI returned a vector with invalid dimension (expected %s)", expected_dim)
            return None
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector):
            logger.error("TEI returned a vector containing non-numeric values")
            return None
        embeddings.append([float(value) for value in vector])
    return embeddings


def embed(texts: list[str]) -> list[list[float]]:
    """Embed *texts*, returning an empty list if TEI is unavailable or invalid."""
    if not texts:
        return []

    try:
        raw = _post_embed_with_retry({"inputs": texts})
    except RetryError:
        logger.error("TEI embedding request failed after 3 attempts", exc_info=True)
        return []
    except Exception:
        logger.error("TEI embedding request failed", exc_info=True)
        return []

    settings = get_settings()
    return _valid_embeddings(raw, len(texts), settings.embedding_dim) or []
