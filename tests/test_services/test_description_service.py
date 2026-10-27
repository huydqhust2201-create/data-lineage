"""Tests for LLM table descriptions. Every LLM invocation is mocked."""

import inspect
from datetime import UTC, datetime
from unittest.mock import Mock

import networkx as nx
import pytest

from src.models.schemas import LineageEdge
from src.services import description_service, graph_service, storage_service


@pytest.fixture(autouse=True)
def _clear_description_cache():
    description_service.get_cache().clear()
    yield
    description_service.get_cache().clear()


@pytest.fixture(autouse=True)
def _fresh_graph():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(1, None)


def _add_edge(source, target, source_column=None, target_column=None, **kw):
    graph_service.add_edge(1,
        LineageEdge(
            source_table=source,
            source_column=source_column,
            target_table=target,
            target_column=target_column,
            confidence=kw.get("confidence", 1.0),
            source_type=kw.get("source_type", "parser"),
            transform_type=kw.get("transform_type", "direct"),
        )
    )


def _record(name: str, **overrides) -> storage_service.NodeRecord:
    values = {
        "current_name": name,
        "defined_in": "models/orders.sql",
        "source_file": "/not/read/orders.sql",
        "columns_produced": ["order_id"],
        "columns_consumed": ["customer_id"],
        "upstream_tables": ["raw.orders"],
        "downstream_tables": ["mart.orders"],
        "source_types": ["parser"],
        "transform_types": ["join"],
        "confidence_min": 0.8,
        "confidence_max": 1.0,
    }
    values.update(overrides)
    return storage_service.NodeRecord(**values)


def _node(**record_overrides) -> storage_service.DescriptionNode:
    return storage_service.DescriptionNode(
        node_id=7,
        record=_record("stg.orders", **record_overrides),
        description=None,
        last_modified=datetime(2026, 8, 18, 9, tzinfo=UTC),
    )


def _mock_llm(monkeypatch, response):
    client = Mock()
    client.invoke.return_value = response
    monkeypatch.setattr(description_service, "_get_description_llm", lambda: client)
    return client


@pytest.mark.parametrize(
    ("label", "expected"),
    list(description_service.DESCRIPTION_CONFIDENCE.items()),
)
def test_description_labels_map_to_fixed_confidence(label, expected, database_id):
    assert description_service.resolve_confidence(label) == expected


def test_unknown_label_uses_default_confidence(database_id):
    assert description_service.resolve_confidence("future_label") == 0.30


def test_llm_numeric_confidence_is_ignored_in_favour_of_label(monkeypatch, database_id):
    _mock_llm(
        monkeypatch,
        {"description": "Prepared reporting orders.", "label": "schema_inferred", "confidence": 0.01},
    )

    result = description_service.describe_tables({"stg.orders": {"name": "stg.orders"}})

    assert description_service.resolve_confidence(result["stg.orders"].label) == 0.75


def test_evidence_hash_changes_when_upstream_columns_change(database_id):
    node = _node()
    before = description_service.build_evidence_payload(node, {"raw.orders": _record("raw.orders")})
    after = description_service.build_evidence_payload(
        node,
        {"raw.orders": _record("raw.orders", columns_produced=["order_id", "order_status"])},
    )

    assert description_service.evidence_hash(before) != description_service.evidence_hash(after)


def test_evidence_hash_is_stable_for_identical_db_data_and_never_reads_files(database_id):
    node = _node()
    neighbours = {"raw.orders": _record("raw.orders")}

    first = description_service.build_evidence_payload(node, neighbours)
    second = description_service.build_evidence_payload(node, neighbours)

    assert description_service.evidence_hash(first) == description_service.evidence_hash(second)
    assert {"ddl", "source_file", "input_path"}.isdisjoint(first)
    assert "input_path" not in inspect.signature(description_service.build_evidence_payload).parameters


def test_evidence_hash_does_not_depend_on_source_file_contents(tmp_path, database_id):
    source_file = tmp_path / "orders.sql"
    source_file.write_text("CREATE TABLE orders (id INT)", encoding="utf-8")
    node = _node(source_file=str(source_file))
    before = description_service.evidence_hash(description_service.build_evidence_payload(node, {}))
    source_file.write_text("CREATE TABLE orders (id INT, note TEXT)", encoding="utf-8")
    source_file.unlink()

    assert before == description_service.evidence_hash(description_service.build_evidence_payload(node, {}))


def test_last_modified_changes_hash(database_id):
    node = _node()
    first = description_service.build_evidence_payload(node, {})
    changed = storage_service.DescriptionNode(
        node_id=node.node_id,
        record=node.record,
        description=None,
        last_modified=datetime(2026, 8, 18, 10, tzinfo=UTC),
    )

    assert description_service.evidence_hash(first) != description_service.evidence_hash(
        description_service.build_evidence_payload(changed, {})
    )


def test_payload_contains_only_one_hop_neighbour_names_and_columns(database_id):
    node = _node()
    payload = description_service.build_evidence_payload(
        node,
        {
            "raw.orders": _record("raw.orders", columns_produced=["raw_order_id"]),
            "mart.orders": _record("mart.orders", columns_consumed=["stg_order_id"]),
        },
    )

    assert payload["upstream"] == [{"name": "raw.orders", "columns": ["customer_id", "raw_order_id"]}]
    assert payload["downstream"] == [{"name": "mart.orders", "columns": ["order_id", "stg_order_id"]}]
    assert "description" not in str(payload)


def test_llm_failure_after_retries_returns_empty_result(monkeypatch, database_id):
    client = Mock()
    client.invoke.side_effect = ConnectionError("OpenRouter unavailable")
    monkeypatch.setattr(description_service, "_get_description_llm", lambda: client)

    assert description_service.describe_tables({"stg.orders": {"name": "stg.orders"}}) == {}
    assert client.invoke.call_count == 3


def test_describe_tables_uses_cache_for_identical_payload(monkeypatch, database_id):
    client = _mock_llm(monkeypatch, {"description": "Prepared reporting orders.", "label": "schema_inferred"})
    payloads = {"stg.orders": {"name": "stg.orders"}}

    assert description_service.describe_tables(payloads)
    assert description_service.describe_tables(payloads)
    assert client.invoke.call_count == 1


def test_parse_response_accepts_json_code_fence(database_id):
    result = description_service._parse_response('```json\n{"description":"Orders.","label":"documented"}\n```')

    assert result == description_service.RawDescription(description="Orders.", label="documented")


def test_build_column_evidence_payload_includes_only_direct_hop_edges(database_id):
    _add_edge("raw.orders", "stg.orders", source_column="id", target_column="order_id", transform_type="direct")
    _add_edge("stg.orders", "mart.summary", source_column="order_id", target_column="total", transform_type="aggregation")

    payload = description_service.build_column_evidence_payload(1, "stg.orders", "order_id")

    assert payload["table"] == "stg.orders"
    assert payload["column"] == "order_id"
    assert payload["produced_by"] == [{"transform_type": "direct", "from_table": "raw.orders", "from_column": "id"}]
    assert payload["consumed_by"] == [
        {"transform_type": "aggregation", "to_table": "mart.summary", "to_column": "total"}
    ]


def test_build_column_evidence_payload_excludes_edges_touching_other_columns(database_id):
    _add_edge("raw.orders", "stg.orders", source_column="id", target_column="order_id")
    _add_edge("raw.orders", "stg.orders", source_column="amount", target_column="amount")

    payload = description_service.build_column_evidence_payload(1, "stg.orders", "order_id")

    assert len(payload["produced_by"]) == 1
    assert payload["produced_by"][0]["from_column"] == "id"


def test_build_column_evidence_payload_is_empty_for_column_with_no_edges(database_id):
    payload = description_service.build_column_evidence_payload(1, "stg.orders", "untouched_column")

    assert payload == {"table": "stg.orders", "column": "untouched_column", "produced_by": [], "consumed_by": []}


def test_describe_columns_uses_column_prompt(monkeypatch, database_id):
    captured_prompts = []

    def fake_invoke(prompt):
        captured_prompts.append(prompt)
        return {"description": "Order identifier.", "label": "schema_inferred"}

    client = Mock()
    client.invoke.side_effect = fake_invoke
    monkeypatch.setattr(description_service, "_get_description_llm", lambda: client)

    description_service.describe_columns({"7:order_id": {"table": "stg.orders", "column": "order_id"}})

    assert captured_prompts[0][0]["content"] == description_service._COLUMN_SYSTEM_PROMPT
    assert description_service._COLUMN_SYSTEM_PROMPT != description_service._SYSTEM_PROMPT


def test_describe_columns_cache_is_independent_of_describe_tables(monkeypatch, database_id):
    client = _mock_llm(monkeypatch, {"description": "Order identifier.", "label": "schema_inferred"})
    payload = {"table": "stg.orders", "column": "order_id"}

    description_service.describe_columns({"7:order_id": payload})
    description_service.describe_tables({"7:order_id": payload})

    assert client.invoke.call_count == 2


def test_table_prompt_limits_scope_and_remains_distinct_from_column_prompt():
    prompt = description_service._SYSTEM_PROMPT.lower()
    assert "at most two sentences" in description_service._SYSTEM_PROMPT
    assert "one to three sentences" not in description_service._SYSTEM_PROMPT
    assert "do not name, list, or explain individual columns" in prompt
    assert "bad:" in prompt
    assert prompt.index("do not name, list, or explain individual columns") < prompt.index('"label"')
    assert description_service._SYSTEM_PROMPT != description_service._COLUMN_SYSTEM_PROMPT
