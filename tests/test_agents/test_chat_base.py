import pytest

from src.agents.chat import base
from src.agents.chat.resolve import TableResolution
from src.services import graph_service


def test_resolve_or_error_returns_trusted_table(monkeypatch):
    monkeypatch.setattr(base, "resolve_table", lambda *_args, **_kwargs: TableResolution(status="resolved", table="ecom.orders"))
    assert base.resolve_or_error("orders", 1) == "ecom.orders"


def test_resolve_or_error_returns_suggestions_without_traversing(monkeypatch):
    monkeypatch.setattr(
        base,
        "resolve_table",
        lambda *_args, **_kwargs: TableResolution(status="not_found", suggestions=["ecom.orders"]),
    )
    monkeypatch.setattr(graph_service, "get_all_tables", lambda: pytest.fail("must not read the graph directly"))
    result = base.resolve_or_error("orderz", 1)
    assert isinstance(result, base.CapabilityResult)
    assert result.error == "table_not_found"
    assert result.extra == {"mention": "orderz", "suggestions": ["ecom.orders"]}


def test_resolve_or_error_keeps_ambiguous_candidates(monkeypatch):
    monkeypatch.setattr(
        base,
        "resolve_table",
        lambda *_args, **_kwargs: TableResolution(status="ambiguous", candidates=["ecom.orders", "stg.orders"]),
    )
    result = base.resolve_or_error("orders", 1)
    assert isinstance(result, base.CapabilityResult)
    assert result.error == "ambiguous"
    assert result.extra["candidates"] == ["ecom.orders", "stg.orders"]
