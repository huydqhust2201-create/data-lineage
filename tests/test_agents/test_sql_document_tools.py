"""Tests for search_sql_content (RAG on ingested SQL text). TEI and storage are mocked."""

import pytest

from src.agents.chat.registry import build_tools
from src.agents.tools.sql_document_tools import SEARCH_SQL_CONTENT_CAPABILITY, SearchSqlContentParams
from src.config import get_settings
from src.services import embedding_service, storage_service


@pytest.fixture(autouse=True)
def _isolate_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
        SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="filter on active customers"), database_id).error
        == "descriptions_disabled"
    )


def test_tei_failure_is_an_error_not_an_exception(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(storage_service, "count_searchable_sql_documents", lambda *_args: 1)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])

    assert (
        SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="filter on active customers"), database_id).error
        == "embedding_unavailable"
    )


def test_empty_index_returns_error_without_calling_tei_or_search(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("empty index must not embed"))
    monkeypatch.setattr(storage_service, "search_sql_documents", lambda *_args: pytest.fail("empty index must not search"))
    monkeypatch.setattr(storage_service, "count_searchable_sql_documents", lambda *_args: 0)

    result = SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="filter on active customers"), database_id)

    assert result.error == "index_empty"


def test_populated_index_with_no_matches_is_a_successful_empty_result(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(storage_service, "count_searchable_sql_documents", lambda *_args: 4)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(storage_service, "search_sql_documents", lambda *_args: [])

    result = SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="no matching SQL"), database_id)

    assert result.error is None
    assert result.extra == {"documents": [], "truncated": True, "total": 4}


def test_vocabulary_contains_table_and_file_names_and_limit_is_capped(monkeypatch, database_id):
    _enable_descriptions(monkeypatch, chat_search_limit=2)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    requested_limits = []

    def search(_database_id, _vector, limit):
        requested_limits.append(limit)
        return [
            ("models/staging/stg_orders.sql", 0, "stg_orders", "select * from raw_orders where status = 'active'", 0.99),
            ("models/marts/customers.sql", 0, "customers", "select * from stg_customers", 0.9),
            ("models/marts/orders.sql", 0, "orders", "select * from stg_orders", 0.8),
        ]

    monkeypatch.setattr(storage_service, "search_sql_documents", search)
    monkeypatch.setattr(storage_service, "count_searchable_sql_documents", lambda *_args: 40)
    result = SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="active customers filter", limit=99), database_id)

    assert requested_limits == [2]
    assert result.extra == {
        "documents": [
            {
                "file_path": "models/staging/stg_orders.sql",
                "statement_order": 0,
                "table": "stg_orders",
                "content": "select * from raw_orders where status = 'active'",
            },
            {
                "file_path": "models/marts/customers.sql",
                "statement_order": 0,
                "table": "customers",
                "content": "select * from stg_customers",
            },
        ],
        "truncated": True,
        "total": 40,
    }
    assert SEARCH_SQL_CONTENT_CAPABILITY.vocabulary(result) == {
        "stg_orders",
        "customers",
        "models/staging/stg_orders.sql",
        "models/marts/customers.sql",
    }


def test_database_failure_returns_safe_error(monkeypatch, database_id):
    _enable_descriptions(monkeypatch)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service, "count_searchable_sql_documents", lambda: (_ for _ in ()).throw(RuntimeError("database down"))
    )

    result = SEARCH_SQL_CONTENT_CAPABILITY.run(SearchSqlContentParams(query="active customers filter"), database_id)

    assert result.error == "search_unavailable"


def test_prompt_rules_distinguish_from_lineage_structure_tools():
    rules = SEARCH_SQL_CONTENT_CAPABILITY.prompt_rules()

    assert "search_sql_content" in rules
    assert "downstream" in rules or "lineage structure" in rules


def test_capability_stays_usable_but_is_deliberately_unregistered():
    """Tool giu nguyen de dua lai re, nhung KHONG dang ky: chi muc SQL cua database
    dang rong (count_searchable_sql_documents = 0) nen no tra total=0 cho moi truy van
    ma khong bao loi, keo model roi khoi traverse. Xem comment o registry.py."""
    assert "SQL" in SEARCH_SQL_CONTENT_CAPABILITY.description
    assert SEARCH_SQL_CONTENT_CAPABILITY.name == "search_sql_content"
    assert all(tool.name != "search_sql_content" for tool in build_tools())
