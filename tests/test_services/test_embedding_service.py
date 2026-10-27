"""Tests for the TEI embedding client. All TEI calls are mocked."""

import pytest

from src.config import get_settings
from src.services import embedding_service


@pytest.fixture(autouse=True)
def _isolate_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _apply_settings(monkeypatch, **overrides):
    for key, value in overrides.items():
        monkeypatch.setenv(key.upper(), str(value))


def test_embed_returns_vectors_from_valid_tei_response(monkeypatch):
    _apply_settings(monkeypatch, embedding_dim=3)
    monkeypatch.setattr(embedding_service, "_post_embed", lambda _payload: [[1, 2.5, -3]])

    assert embedding_service.embed(["orders table"]) == [[1.0, 2.5, -3.0]]


def test_embed_rejects_vectors_with_wrong_dimension(monkeypatch):
    _apply_settings(monkeypatch, embedding_dim=3)
    monkeypatch.setattr(embedding_service, "_post_embed", lambda _payload: [[1.0, 2.0]])

    assert embedding_service.embed(["orders table"]) == []


def test_embed_rejects_response_with_missing_vector(monkeypatch):
    _apply_settings(monkeypatch, embedding_dim=3)
    monkeypatch.setattr(embedding_service, "_post_embed", lambda _payload: [[1.0, 2.0, 3.0]])

    assert embedding_service.embed(["orders", "customers"]) == []


def test_embed_returns_empty_after_three_network_failures(monkeypatch):
    _apply_settings(monkeypatch, embedding_dim=3)
    attempts = 0

    def unavailable(_payload):
        nonlocal attempts
        attempts += 1
        raise ConnectionError("TEI unavailable")

    monkeypatch.setattr(embedding_service, "_post_embed", unavailable)

    assert embedding_service.embed(["orders"]) == []
    assert attempts == 3
