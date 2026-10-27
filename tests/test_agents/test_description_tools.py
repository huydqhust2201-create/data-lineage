"""Tests for semantic description search. TEI and storage are mocked."""

import networkx as nx
import pytest

from src.agents.chat.registry import build_tools
from src.agents.tools.description_tools import (
    SEARCH_BY_DESCRIPTION_CAPABILITY,
    SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY,
    SearchByDescriptionParams,
    SearchColumnByDescriptionParams,
)
from src.config import get_settings
from src.services import embedding_service, graph_service, storage_service


@pytest.fixture(autouse=True)
def _isolate_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_graph(database_id):
    graph_service._reset_graph(database_id, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(database_id, None)


def _enable_descriptions(monkeypatch, **settings):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    for key, value in settings.items():
        monkeypatch.setenv(key.upper(), str(value))
    get_settings.cache_clear()


def test_disabled_does_not_call_tei(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("TEI must not run"))

    assert (
        SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="customer lifetime value"), database_id).error
        == "descriptions_disabled"
    )


def test_tei_failure_is_an_error_not_an_exception(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(storage_service, "count_searchable_descriptions", lambda *_args: 1)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])

    assert (
        SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="customer lifetime value"), database_id).error
        == "embedding_unavailable"
    )


def test_empty_table_description_index_returns_error_without_calling_tei_or_search(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("empty index must not embed"))
    monkeypatch.setattr(storage_service, "search_descriptions", lambda *_args: pytest.fail("empty index must not search"))
    monkeypatch.setattr(storage_service, "count_searchable_descriptions", lambda *_args: 0)

    result = SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="customer lifetime value"), database_id)

    assert result.error == "index_empty"


def test_populated_table_description_index_with_no_matches_is_successful(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(storage_service, "count_searchable_descriptions", lambda *_args: 4)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(storage_service, "search_descriptions", lambda *_args: [])

    result = SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="no matching description"), database_id)

    assert result.error is None
    assert result.extra == {"tables": [], "truncated": True, "total": 4}


def test_vocabulary_contains_only_table_names_and_limit_is_capped(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    requested_limits = []

    def search(_database_id, _vector, limit):
        requested_limits.append(limit)
        return [
            ("mart.customer_ltv", "Lifetime value facts and customer revenue.", 0.99),
            ("mart.customer_segments", "Customer segmentation.", 0.9),
            ("raw.customers", "Customer profile.", 0.8),
        ]

    monkeypatch.setattr(storage_service, "search_descriptions", search)
    monkeypatch.setattr(storage_service, "count_searchable_descriptions", lambda *_args: 40)
    result = SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="customer lifetime value", limit=99), database_id)

    assert requested_limits == [2]
    assert result.extra == {"tables": ["mart.customer_ltv", "mart.customer_segments"], "truncated": True, "total": 40}
    assert SEARCH_BY_DESCRIPTION_CAPABILITY.vocabulary(result) == {"mart.customer_ltv", "mart.customer_segments"}
    assert "Lifetime" not in SEARCH_BY_DESCRIPTION_CAPABILITY.vocabulary(result)


def test_database_failure_returns_safe_error(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service, "count_searchable_descriptions", lambda: (_ for _ in ()).throw(RuntimeError("database down"))
    )

    result = SEARCH_BY_DESCRIPTION_CAPABILITY.run(SearchByDescriptionParams(query="customer lifetime value"), database_id)

    assert result.error == "search_unavailable"


def test_prompt_rules_prefer_description_search_over_table_name_search(database_id):
    rules = SEARCH_BY_DESCRIPTION_CAPABILITY.prompt_rules()

    assert "search_by_description" in rules
    assert "search_tables" in rules
    assert "not search_tables" in rules
    assert "score" not in rules
    assert "most relevant" not in rules


def test_description_is_exposed_in_tool_schema_without_score_claims(database_id):
    description = SEARCH_BY_DESCRIPTION_CAPABILITY.description
    tool = next(tool for tool in build_tools() if tool.name == "search_by_description")

    assert "meaning" in description
    assert "purpose" in description
    assert "score" not in description
    assert "most relevant" not in description
    assert tool.description == description


def test_column_search_disabled_does_not_call_tei(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("TEI must not run"))

    assert (
        SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="order id"), database_id).error
        == "descriptions_disabled"
    )


def test_column_search_tei_failure_is_an_error_not_an_exception(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(storage_service, "count_searchable_column_descriptions", lambda *_args: 1)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])

    assert (
        SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="order id"), database_id).error
        == "embedding_unavailable"
    )


def test_empty_column_description_index_returns_error_without_calling_tei_or_search(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("empty index must not embed"))
    monkeypatch.setattr(storage_service, "search_column_descriptions", lambda *_args: pytest.fail("empty index must not search"))
    monkeypatch.setattr(storage_service, "count_searchable_column_descriptions", lambda *_args: 0)

    result = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="order id"), database_id)

    assert result.error == "index_empty"


def test_populated_column_description_index_with_no_matches_is_successful(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(storage_service, "count_searchable_column_descriptions", lambda *_args: 4)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(storage_service, "search_column_descriptions", lambda *_args: [])

    result = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="no matching column"), database_id)

    assert result.error is None
    assert result.extra == {"columns": [], "truncated": True, "total": 4, "match_kind": "none"}


def test_column_search_vocabulary_contains_table_and_column_names_and_limit_is_capped(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    requested_limits = []

    def search(_database_id, _vector, limit):
        requested_limits.append(limit)
        return [
            ("mart.customer_ltv", "lifetime_value", "Total lifetime revenue per customer.", 0.99),
            ("mart.orders", "order_id", "Primary key of the order.", 0.9),
            ("raw.customers", "customer_id", "Customer identifier.", 0.8),
        ]

    monkeypatch.setattr(storage_service, "search_column_descriptions", search)
    monkeypatch.setattr(storage_service, "count_searchable_column_descriptions", lambda *_args: 40)
    result = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="lifetime value", limit=99), database_id)

    assert requested_limits == [2]
    assert result.extra == {
        "columns": [
            {"table": "mart.customer_ltv", "column": "lifetime_value", "description": "Total lifetime revenue per customer."},
            {"table": "mart.orders", "column": "order_id", "description": "Primary key of the order."},
        ],
        "truncated": True,
        "total": 40,
        "match_kind": "semantic",
    }
    assert SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.vocabulary(result) == {
        "mart.customer_ltv",
        "lifetime_value",
        "mart.orders",
        "order_id",
    }


def test_column_exact_name_match_keeps_stored_description(monkeypatch, database_id):
    from types import SimpleNamespace

    from src.models.schemas import LineageEdge
    edge = LineageEdge(
            source_table="stg.invoices",
            source_column="amount_paid",
            target_table="mart.revenue",
            target_column="amount_paid",
            confidence=1.0,
            source_type="parser",
    )
    monkeypatch.setattr(graph_service, "get_all_edges", lambda _database_id: [edge])
    monkeypatch.setattr(
        storage_service,
        "load_column_descriptions_by_names",
        lambda *_args: {("stg.invoices", "amount_paid"): SimpleNamespace(description="Paid amount on an invoice.")},
    )
    monkeypatch.setattr(storage_service, "count_searchable_column_descriptions", lambda *_args: 0)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("exact match must not embed"))

    result = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="amount_paid"), database_id)

    assert result.extra["match_kind"] == "exact"
    assert result.extra["columns"] == [
        {"table": "mart.revenue", "column": "amount_paid", "description": None},
        {"table": "stg.invoices", "column": "amount_paid", "description": "Paid amount on an invoice."},
    ]
    assert SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.vocabulary(result) == {
        "mart.revenue",
        "amount_paid",
        "stg.invoices",
    }


def test_column_search_database_failure_returns_safe_error(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service,
        "count_searchable_column_descriptions",
        lambda: (_ for _ in ()).throw(RuntimeError("database down")),
    )

    result = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.run(SearchColumnByDescriptionParams(query="order id"), database_id)

    assert result.error == "search_unavailable"


def test_column_search_prompt_rules_distinguish_from_table_search(database_id):
    rules = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.prompt_rules()

    assert "search_column_description" in rules
    assert "search_by_description" in rules


def test_column_search_description_is_exposed_in_tool_schema(database_id):
    description = SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.description
    tool = next(tool for tool in build_tools() if tool.name == "search_column_description")

    assert "column" in description
    assert tool.description == description
