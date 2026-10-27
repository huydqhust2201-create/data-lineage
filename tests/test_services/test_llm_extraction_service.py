"""Tests for llm_extraction_service — v3 improvements.

Covers:
  1. File-Based Cache (SHA-256)
  2. Retry & Circuit Breaker (tenacity)
  3. Prompt v3 (resolution_method, union transform, and columns)
  + Full backward compatibility with original test cases.
"""

import json
from unittest.mock import Mock

import pytest

from src.services import llm_extraction_service as service
from src.services.naming import normalize_table_name

# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def raw_edge(**overrides):
    edge = {
        "source_table": "raw.orders",
        "target_table": "stg_orders",
        "transform_type": "direct",
        "confidence": 0.7,
        "reasoning": "Test fixture reasoning",
    }
    edge.update(overrides)
    return edge


def mock_client(monkeypatch, response):
    client = Mock()
    client.invoke.return_value = response
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)
    return client


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with a clean cache."""
    service.get_cache().clear()
    yield
    service.get_cache().clear()


# ═══════════════════════════════════════════════════════════════════════════════
#  Backward compatibility tests (same as original)
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_prompt_contains_context():
    prompt = service._build_prompt("select * from raw.orders", "orders.sql", "postgres")
    assert "orders.sql" in prompt[1]["content"]
    assert "postgres" in prompt[1]["content"]
    assert "select * from raw.orders" in prompt[1]["content"]


@pytest.mark.parametrize(
    "raw",
    [
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge())]),
        {"edges": [raw_edge()]},
        json.dumps({"edges": [raw_edge()]}),
        "```json\n" + json.dumps({"edges": [raw_edge()]}) + "\n```",
    ],
)
def test_parse_response_supported_shapes(raw):
    assert len(service._parse_response(raw).edges) == 1


def test_parse_response_malformed_is_empty():
    assert service._parse_response("not json").edges == []


def test_parse_response_uses_content_attribute():
    response = type("Message", (), {"content": json.dumps({"edges": [raw_edge()]})})()
    assert len(service._parse_response(response).edges) == 1


@pytest.mark.parametrize(
    "raw",
    [42, {"edges": "invalid"}, {"unresolved": [1]}, {"edges": [{"source_table": "x"}]}],
)
def test_parse_response_invalid_shapes_are_empty(raw):
    assert service._parse_response(raw).edges == []


def test_edges_have_llm_contract(monkeypatch):
    mock_client(monkeypatch, {"edges": [raw_edge(confidence=1.0)]})
    edge = service.extract_edges("select 1")[0]
    assert edge.source_type == "llm"
    assert edge.confidence < 1.0
    assert edge.source_column is None and edge.target_column is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('"RAW"."Orders"', "RAW.Orders"),
        ("`raw.orders`", "raw.orders"),
        ("[raw].[orders]", "raw.orders"),
        ("  RAW.ORDERS ;", "raw.orders"),
    ],
)
def test_normalize_table(name, expected):
    assert normalize_table_name(name, "postgres") == expected


def test_quoted_identifier_keeps_case():
    assert normalize_table_name('"RAW"."Orders"', "postgres") == "RAW.Orders"


def test_normalization_uses_requested_dialect():
    assert normalize_table_name("Orders", "postgres") == "orders"
    assert normalize_table_name("Orders", "snowflake") == "ORDERS"


def test_jinja_and_self_loop_are_dropped(caplog):
    caplog.set_level("DEBUG", logger=service.__name__)
    response = service.ExtractionResponse(
        edges=[
            service.RawEdge(**raw_edge(source_table="{{ ref('orders') }}")),
            service.RawEdge(**raw_edge(target_table="raw.orders")),
        ]
    )
    assert service.to_lineage_edges(response, "model.sql") == []
    assert "model.sql" in caplog.text


def test_duplicates_keep_highest_and_ordering():
    response = service.ExtractionResponse(
        edges=[
            service.RawEdge(**raw_edge(source_table="raw.z", confidence=0.4)),
            service.RawEdge(**raw_edge(source_table="raw.a", confidence=0.6)),
            service.RawEdge(**raw_edge(source_table="raw.z", confidence=0.8)),
        ]
    )
    edges = service.to_lineage_edges(response)
    assert [e.source_table for e in edges] == ["raw.a", "raw.z"]
    assert edges[1].confidence == 0.8


def test_empty_input_does_not_call_llm(monkeypatch):
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})
    assert service.extract_edges("  \n") == []
    client.invoke.assert_not_called()


def test_extract_raw_empty_input(monkeypatch):
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})
    assert service.extract_raw("").edges == []
    client.invoke.assert_not_called()


def test_extract_raw_returns_response(monkeypatch):
    mock_client(monkeypatch, {"edges": [raw_edge()]})
    response = service.extract_raw("select 1")
    assert isinstance(response, service.ExtractionResponse)
    assert len(response.edges) == 1


def test_extract_from_files_survives_missing(monkeypatch, tmp_path):
    path = tmp_path / "model.sql"
    path.write_text("select 1", encoding="utf-8")
    mock_client(monkeypatch, {"edges": [raw_edge()]})
    result = service.extract_edges_from_files([str(path), str(tmp_path / "missing.sql")])
    assert len(result[str(path)]) == 1
    assert result[str(tmp_path / "missing.sql")] == []


def test_extract_from_file_uses_file_stem(monkeypatch, tmp_path):
    path = tmp_path / "orders.sql"
    path.write_text("select 1", encoding="utf-8")
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})
    assert len(service.extract_edges_from_file(str(path))) == 1
    assert "orders" in client.invoke.call_args.args[0][1]["content"]


# ═══════════════════════════════════════════════════════════════════════════════
#  V2 Feature 1: File-Based Cache (SHA-256)
# ═══════════════════════════════════════════════════════════════════════════════


def test_cache_hit_skips_llm_call(monkeypatch):
    """Second call with same content returns cached result, no LLM call."""
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})

    # First call — LLM invoked
    r1 = service.extract_raw("select * from t1", "model.sql")
    assert len(r1.edges) == 1
    assert client.invoke.call_count == 1

    # Second call — same content → cache HIT, no LLM
    r2 = service.extract_raw("select * from t1", "model.sql")
    assert len(r2.edges) == 1
    assert client.invoke.call_count == 1  # still 1 — no new call

    stats = service.get_cache().stats
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_cache_miss_on_different_content(monkeypatch):
    """Different SQL content should produce a cache miss."""
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})
    service.extract_raw("select 1", "a.sql")
    service.extract_raw("select 2", "a.sql")
    assert client.invoke.call_count == 2

    stats = service.get_cache().stats
    assert stats["misses"] == 2


def test_cache_miss_on_different_file_name(monkeypatch):
    """Same SQL but different file name → different cache key."""
    client = mock_client(monkeypatch, {"edges": [raw_edge()]})
    service.extract_raw("select 1", "model_a.sql")
    service.extract_raw("select 1", "model_b.sql")
    assert client.invoke.call_count == 2


def test_cache_key_is_sha256():
    """Cache key must be a valid SHA-256 hex digest."""
    key = service._cache.make_key("content", "file", "postgres")
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_cache_clear_resets_everything(monkeypatch):
    """After clear(), previously cached items are gone."""
    mock_client(monkeypatch, {"edges": [raw_edge()]})
    service.extract_raw("select 1", "m.sql")
    assert service.get_cache().stats["size"] == 1

    service.get_cache().clear()
    assert service.get_cache().stats["size"] == 0
    assert service.get_cache().stats["hits"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  V2 Feature 2: Retry & Circuit Breaker (tenacity)
# ═══════════════════════════════════════════════════════════════════════════════


def test_retry_succeeds_on_second_attempt(monkeypatch):
    """LLM fails once then succeeds → caller gets result, no crash."""
    call_count = 0

    def flaky_invoke(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Rate limit")
        return {"edges": [raw_edge()]}

    client = Mock()
    client.invoke.side_effect = flaky_invoke
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)

    result = service.extract_raw("select 1")
    assert len(result.edges) == 1
    assert call_count == 2  # first fail + second success


def test_retry_exhausted_returns_empty(monkeypatch, caplog):
    """After 3 retries all fail → empty result, 'SYSTEM_ERROR' in log."""
    client = Mock()
    client.invoke.side_effect = ConnectionError("timeout")
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)

    result = service.extract_raw("select 1", "broken.sql")
    assert result.edges == []
    assert "SYSTEM_ERROR" in caplog.text
    assert "broken.sql" in caplog.text


def test_retry_exhausted_does_not_crash_pipeline(monkeypatch, tmp_path):
    """extract_edges_from_files should survive individual file failures."""
    good_path = tmp_path / "good.sql"
    good_path.write_text("select 1", encoding="utf-8")

    bad_path = tmp_path / "bad.sql"
    bad_path.write_text("select 2", encoding="utf-8")

    call_count = 0

    def selective_invoke(prompt):
        nonlocal call_count
        call_count += 1
        user_msg = prompt[1]["content"]
        if "select 2" in user_msg:
            raise TimeoutError("API timeout")
        return {"edges": [raw_edge()]}

    client = Mock()
    client.invoke.side_effect = selective_invoke
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)

    results = service.extract_edges_from_files([str(good_path), str(bad_path)])
    # good file should succeed
    assert len(results[str(good_path)]) == 1
    # bad file should return empty, not crash
    assert results[str(bad_path)] == []


# ═══════════════════════════════════════════════════════════════════════════════
#  V3 Feature 3: Prompt v3 — resolution_method, union transform, and columns
# ═══════════════════════════════════════════════════════════════════════════════


def test_prompt_version_is_v4():
    assert service.PROMPT_VERSION == "v4"


def test_system_prompt_loaded_from_file():
    """System prompt should be loaded from _llm_prompt_v4.txt."""
    assert service._PROMPT_V4_PATH.name == "_llm_prompt_v4.txt"
    assert "resolution_method" in service._SYSTEM_PROMPT
    assert "GOLDEN RULES" in service._SYSTEM_PROMPT
    assert "source_column" in service._SYSTEM_PROMPT
    assert "transform_expression" in service._SYSTEM_PROMPT
    forbidden_instruction = "Emit only " + "table-level edges"
    assert forbidden_instruction not in service._SYSTEM_PROMPT


def test_transform_expression_survives_conversion_and_is_citation_verified():
    sql = "SELECT SUM(amount_paid) AS total_revenue FROM stg_invoices"
    edge = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(
                    **raw_edge(
                        source_column="amount_paid",
                        target_column="total_revenue",
                        transform_type="aggregation",
                        transform_expression="SUM(amount_paid) AS total_revenue",
                    )
                )
            ]
        ),
        raw_sql=sql,
    )[0]
    assert edge.evidence.transform_expression == "SUM(amount_paid) AS total_revenue"
    assert edge.evidence.citation_verified is True


@pytest.mark.parametrize(
    ("matched_text", "transform_expression", "expected"),
    [
        (None, "SUM(missing) AS total", False),
        ("FROM stg_invoices", "SUM(missing) AS total", False),
        (None, "SUM(amount_paid) AS total_revenue", True),
        (None, None, None),
    ],
)
def test_transform_expression_citation_truth_table(matched_text, transform_expression, expected):
    edge = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(
                    **raw_edge(
                        source_column="amount_paid",
                        target_column="total_revenue",
                        matched_text=matched_text,
                        transform_expression=transform_expression,
                    )
                )
            ]
        ),
        raw_sql="SELECT SUM(amount_paid) AS total_revenue FROM stg_invoices",
    )[0]
    assert edge.evidence.citation_verified is expected


def test_table_level_llm_edge_discards_transform_expression():
    edge = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(
                    **raw_edge(transform_expression="SELECT * FROM raw.orders", matched_text="SELECT * FROM raw.orders")
                )
            ]
        ),
        raw_sql="SELECT * FROM raw.orders",
    )[0]
    assert edge.source_column is None and edge.target_column is None
    assert edge.evidence.transform_expression is None
    assert edge.evidence.citation_verified is True


@pytest.mark.parametrize(
    ("method", "expected_conf"),
    [
        ("static", 0.90),
        ("ref_source", 0.70),
        ("branch", 0.50),
        ("dynamic", 0.40),
        ("macro", 0.35),
        ("speculative", 0.25),
    ],
)
def test_resolution_method_maps_to_confidence(method, expected_conf):
    raw = service.RawEdge(
        source_table="a",
        target_table="b",
        resolution_method=method,
    )
    assert service._resolve_confidence(raw) == expected_conf


def test_unknown_resolution_method_uses_default():
    raw = service.RawEdge(
        source_table="a",
        target_table="b",
        resolution_method="some_future_method",
    )
    assert service._resolve_confidence(raw) == 0.50


def test_no_resolution_method_falls_back_to_confidence():
    """When resolution_method is None, use raw confidence (v1 compat)."""
    raw = service.RawEdge(
        source_table="a",
        target_table="b",
        confidence=0.85,
    )
    assert service._resolve_confidence(raw) == 0.85


def test_resolution_method_overrides_confidence(monkeypatch):
    """When LLM returns both, resolution_method takes priority."""
    mock_client(
        monkeypatch,
        {
            "edges": [
                raw_edge(
                    resolution_method="static",
                    confidence=0.5,  # should be ignored
                )
            ]
        },
    )
    edges = service.extract_edges("select 1")
    assert len(edges) == 1
    assert edges[0].confidence == 0.90  # from "static" mapping


def test_union_transform_type_accepted_but_mapped(monkeypatch):
    """v2 prompt can return 'union' but schema maps it to 'unknown'."""
    mock_client(monkeypatch, {"edges": [raw_edge(transform_type="union")]})
    edges = service.extract_edges("select 1")
    assert len(edges) == 1
    # "union" is in VALID_TRANSFORM_TYPES but mapped to "unknown"
    # for LineageEdge schema compatibility
    assert edges[0].transform_type == "unknown"


def test_valid_v2_response_with_resolution_method(monkeypatch):
    """Full v2 response with resolution_method and reasoning."""
    v2_edge = {
        "source_table": "raw_events",
        "target_table": "daily_metrics",
        "transform_type": "aggregation",
        "resolution_method": "static",
        "reasoning": "Traced through CTE to base table raw_events.",
    }
    mock_client(monkeypatch, {"edges": [v2_edge], "unresolved": []})
    edges = service.extract_edges(
        "select count(*) from raw_events group by 1",
        file_path="daily_metrics.sql",
    )
    assert len(edges) == 1
    assert edges[0].source_table == "raw_events"
    assert edges[0].target_table == "daily_metrics"
    assert edges[0].transform_type == "aggregation"
    assert edges[0].confidence == 0.90  # "static" → 0.90


def test_raw_edge_has_resolution_method_field():
    """RawEdge model should accept resolution_method."""
    edge = service.RawEdge(
        source_table="a",
        target_table="b",
        resolution_method="ref_source",
    )
    assert edge.resolution_method == "ref_source"


def test_raw_edge_resolution_method_optional():
    """resolution_method is optional for backward compat."""
    edge = service.RawEdge(source_table="a", target_table="b")
    assert edge.resolution_method is None


def test_reasoning_detail_carried_into_evidence():
    """`reasoning_detail` from the LLM lands on evidence, distinct from `reasoning`."""
    edges = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(
                    source_table="raw.orders",
                    target_table="stg_orders",
                    reasoning="Ngắn gọn.",
                    reasoning_detail="Giải thích dài hơn về căn cứ trong SQL và mức tin cậy.",
                )
            ]
        )
    )
    assert edges[0].evidence.reasoning == "Ngắn gọn."
    assert edges[0].evidence.reasoning_detail == "Giải thích dài hơn về căn cứ trong SQL và mức tin cậy."


@pytest.mark.parametrize("detail", [None, "", "   "])
def test_missing_reasoning_detail_falls_back_to_placeholder(detail):
    edge = service.to_lineage_edges(
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge(reasoning_detail=detail))])
    )[0]
    assert edge.evidence.reasoning_detail == service._MISSING_REASONING_DETAIL_PLACEHOLDER


def test_resolution_method_carried_into_evidence_normalized():
    edge = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[service.RawEdge(**raw_edge(resolution_method=" Ref_Source "))]
        )
    )[0]
    assert edge.evidence.resolution_method == "ref_source"


def test_missing_resolution_method_stays_none():
    edge = service.to_lineage_edges(
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge())])
    )[0]
    assert edge.evidence.resolution_method is None


def test_dependency_kind_default_output_and_control_forces_null_target_column():
    edges = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(**raw_edge(source_column="a", target_column="a")),
                service.RawEdge(
                    **raw_edge(source_column="age", target_column="age", dependency_kind="filter")
                ),
            ]
        )
    )
    by_kind = {e.dependency_kind: e for e in edges}
    assert by_kind["output"].target_column == "a"
    assert by_kind["filter"].target_column is None  # control edge -> target_column bị ép null


def test_invalid_dependency_kind_falls_back_to_output():
    edge = service.to_lineage_edges(
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge(dependency_kind="wat"))])
    )[0]
    assert edge.dependency_kind == "output"


def test_conditional_transform_type_accepted():
    edge = service.to_lineage_edges(
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge(transform_type="conditional"))])
    )[0]
    assert edge.transform_type == "conditional"


def test_column_fields_are_preserved_and_normalized():
    edges = service.to_lineage_edges(
        service.ExtractionResponse(
            edges=[
                service.RawEdge(
                    source_table="raw.orders",
                    source_column="  orders.amount ",
                    target_table="daily_revenue",
                    target_column=" total_revenue ",
                    transform_type="aggregation",
                )
            ]
        )
    )
    assert [(edge.source_column, edge.target_column) for edge in edges] == [("amount", "total_revenue")]


def test_column_deduplication_keeps_distinct_mappings_and_best_duplicate():
    response = service.ExtractionResponse(
        edges=[
            service.RawEdge(**raw_edge(source_column="total_revenue", target_column="projected_revenue", confidence=0.4)),
            service.RawEdge(**raw_edge(source_column="total_revenue", target_column="projected_revenue", confidence=0.8)),
            service.RawEdge(**raw_edge(source_column="department_id", target_column="department_id", confidence=0.7)),
        ]
    )
    edges = service.to_lineage_edges(response)
    assert {(edge.source_column, edge.target_column) for edge in edges} == {
        ("total_revenue", "projected_revenue"),
        ("department_id", "department_id"),
    }
    assert next(edge for edge in edges if edge.source_column == "total_revenue").confidence == 0.8


@pytest.mark.parametrize("source_column", [None, "", "  "])
def test_blank_column_is_normalized_to_none(source_column):
    edge = service.to_lineage_edges(
        service.ExtractionResponse(edges=[service.RawEdge(**raw_edge(source_column=source_column))])
    )[0]
    assert edge.source_column is None


def test_column_fields_survive_public_extraction_path(monkeypatch):
    mock_client(monkeypatch, {"edges": [
        raw_edge(source_table="department_revenue", source_column="total_revenue", target_table="revenue_alerts_staging", target_column="projected_revenue"),
        raw_edge(source_table="department_revenue", source_column="department_id", target_table="revenue_alerts_staging", target_column="department_id"),
    ]})
    edges = service.extract_edges("select 1", file_name="revenue_alerts_staging")
    assert {(edge.source_column, edge.target_column) for edge in edges} == {
        ("total_revenue", "projected_revenue"),
        ("department_id", "department_id"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Combined: Cache + Retry interaction
# ═══════════════════════════════════════════════════════════════════════════════


def test_cache_not_populated_on_retry_failure(monkeypatch):
    """If all retries fail, nothing is cached (so next attempt can retry)."""
    client = Mock()
    client.invoke.side_effect = RuntimeError("boom")
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)

    service.extract_raw("select 1", "fail.sql")
    assert service.get_cache().stats["size"] == 0


def test_cache_populated_after_successful_retry(monkeypatch):
    """If retry succeeds on 2nd attempt, result should be cached."""
    call_count = 0

    def flaky(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("transient")
        return {"edges": [raw_edge()]}

    client = Mock()
    client.invoke.side_effect = flaky
    monkeypatch.setattr(service, "_get_extraction_llm", lambda: client)

    r1 = service.extract_raw("select 1", "retry_ok.sql")
    assert len(r1.edges) == 1
    assert service.get_cache().stats["size"] == 1

    # Third call should hit cache (no more LLM calls)
    r2 = service.extract_raw("select 1", "retry_ok.sql")
    assert len(r2.edges) == 1
    assert call_count == 2  # no additional calls
