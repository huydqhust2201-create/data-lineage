import networkx as nx
import pytest
from pydantic import BaseModel

from src.agents.chat import guard, resolve
from src.agents.chat.base import CapabilityResult, edge_fingerprint
from src.agents.chat.registry import REGISTRY, build_tools, merged_prompt_rules
from src.agents.tools.asset_tools import GET_ASSET_CAPABILITY, GetAssetParams
from src.agents.tools.breaking_change_tools import BREAKING_CHANGES_CAPABILITY, BreakingChangesParams
from src.agents.tools.impact_tools import (
    ASSESS_CHANGE_CAPABILITY,
    TRAVERSE_CAPABILITY,
    AssessChangeParams,
    TraverseParams,
)
from src.agents.tools.query_tools import ANALYZE_QUERY_CAPABILITY, AnalyzeQueryParams
from src.models.schemas import LineageEdge, LineageEvidence
from src.services import graph_service, impact_service, review_service, storage_service


@pytest.fixture(autouse=True)
def fresh_lineage():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(1, None)
    review_service._reset()


def add_edge(source, target, **kwargs):
    graph_service.add_edge(1,
        LineageEdge(source_table=source, target_table=target, confidence=1.0, source_type="parser", **kwargs)
    )


def test_traverse_returns_confirmed_and_pending_separately():
    add_edge("ecom.orders", "stg.orders")
    review_service.add_pending(1,
        [LineageEdge(source_table="stg.orders", target_table="legacy_ltv", confidence=0.5, source_type="llm")]
    )
    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="ecom.orders", direction="downstream"), 1)
    assert [edge.target_table for edge in result.confirmed] == ["stg.orders"]
    assert [edge.target_table for edge in result.pending] == ["legacy_ltv"]
    assert TRAVERSE_CAPABILITY.vocabulary(result) == {"ecom.orders", "stg.orders", "legacy_ltv"}


def test_unknown_table_does_not_traverse_graph(monkeypatch):
    add_edge("ecom.orders", "stg.orders")
    monkeypatch.setattr(impact_service, "query_impact_edges", lambda *_: pytest.fail("must not traverse"))
    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="missing_table", direction="downstream"), 1)
    assert result.error == "table_not_found"
    assert result.extra["mention"] == "missing_table"


def test_traverse_uses_a_known_column_when_the_table_name_is_invalid():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")

    result = TRAVERSE_CAPABILITY.run(
        TraverseParams(table="*", column="amount_paid", direction="downstream"), 1
    )

    assert result.error is None
    assert result.extra["resolved_table"] == "raw.invoices"
    assert result.extra["resolved_column"] == "amount_paid"


def test_traverse_keeps_the_invalid_table_error_for_an_unknown_column():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")

    result = TRAVERSE_CAPABILITY.run(
        TraverseParams(table="*", column="missing_column", direction="downstream"), 1
    )

    assert result.error == "table_not_found"
    assert result.extra["mention"] == "*"


def test_traverse_returns_ambiguous_for_an_invalid_table_and_independent_shared_column():
    add_edge("raw.invoices", "stg.invoices", source_column="amount", target_column="invoice_amount")
    add_edge("raw.payments", "stg.payments", source_column="amount", target_column="payment_amount")

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="*", column="amount", direction="upstream"), 1)

    assert result.error == "ambiguous"
    assert result.extra["candidates"] == ["raw.invoices", "raw.payments"]


def test_ambiguous_table_does_not_traverse_graph(monkeypatch):
    add_edge("ecom.orders", "stg.orders")
    monkeypatch.setattr(impact_service, "query_impact_edges", lambda *_: pytest.fail("must not traverse"))
    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="orders", direction="downstream"), 1)
    assert result.error == "ambiguous"
    assert result.extra["candidates"] == ["ecom.orders", "stg.orders"]


def test_upstream_hops_use_source_table_and_column_note():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "fct_sales", target_column="total_amount")
    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="fct_sales", column="total_amount", direction="upstream"), 1)
    assert [result.extra["hops_by_edge"][edge_fingerprint(edge)] for edge in result.confirmed] == [1, 2]
    assert "nhiều hop" in result.extra["column_filter_note"]


@pytest.mark.parametrize(("direction", "table"), [("downstream", "ecom.orders"), ("upstream", "stg.orders")])
def test_traverse_returns_expected_edges_in_each_direction(direction, table):
    add_edge("ecom.orders", "stg.orders")
    review_service.add_pending(
        1, [LineageEdge(source_table="legacy.orders", target_table="stg.orders", confidence=0.5, source_type="llm")]
    )

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table=table, direction=direction), 1)

    assert [(edge.source_table, edge.target_table) for edge in result.confirmed] == [("ecom.orders", "stg.orders")]
    expected_pending = [("legacy.orders", "stg.orders")] if direction == "upstream" else []
    assert [(edge.source_table, edge.target_table) for edge in result.pending] == expected_pending


def test_traverse_depth_excludes_pending_beyond_the_limit():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "mart.orders")
    review_service.add_pending(
        1, [LineageEdge(source_table="stg.orders", target_table="report", confidence=0.5, source_type="llm")]
    )

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="raw.orders", direction="downstream", depth=1), 1)

    assert [(edge.source_table, edge.target_table) for edge in result.confirmed] == [("raw.orders", "stg.orders")]
    assert result.pending == []


def test_assess_change_returns_risk_notes_for_confirmed_edges():
    add_edge("ecom.orders", "stg.orders", transform_type="join")
    result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="type"), 1)
    (edge,) = result.confirmed
    note = result.extra["risk_by_edge"][edge_fingerprint(edge)]
    assert "cao" in note and "join" in note


def test_lineage_capabilities_return_candidates_when_a_column_does_not_resolve():
    add_edge("ecom.orders", "stg.orders", source_column="order_id", target_column="order_id")

    traverse = TRAVERSE_CAPABILITY.run(
        TraverseParams(table="ecom.orders", column="missing_column", direction="downstream"), 1
    )
    assess = ASSESS_CHANGE_CAPABILITY.run(
        AssessChangeParams(table="ecom.orders", column="missing_column", change_kind="type"), 1
    )

    assert traverse.error == "column_not_found"
    assert assess.error == "column_not_found"
    assert traverse.extra["candidates"] == ["order_id"]
    assert assess.extra["candidates"] == ["order_id"]


def test_traverse_resolves_a_column_mention_to_its_downstream_chain_entry():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")
    add_edge("stg.invoices", "department_revenue", source_column="amount_paid", target_column="amount_paid")

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="amount_paid", direction="downstream"), 1)

    assert result.error is None
    assert result.extra["resolved_table"] == "raw.invoices"


def test_traverse_returns_ambiguous_when_a_column_has_no_directional_chain_entry():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")
    add_edge("other.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="amount_paid", direction="downstream"), 1)

    assert result.error == "ambiguous"
    assert result.extra["candidates"] == ["other.invoices", "raw.invoices"]


def test_column_resolution_changes_with_the_requested_direction_and_is_safe_without_one():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")
    add_edge("other.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")

    upstream = TRAVERSE_CAPABILITY.run(TraverseParams(table="amount_paid", direction="upstream"), 1)
    no_direction = resolve.resolve_table("amount_paid", database_id=1)

    assert upstream.error is None
    assert upstream.extra["resolved_table"] == "stg.invoices"
    assert no_direction.status == "ambiguous"
    assert no_direction.candidates == ["other.invoices", "raw.invoices", "stg.invoices"]


@pytest.mark.parametrize("direction", ["upstream", "downstream"])
def test_column_cycle_returns_real_candidates_instead_of_an_empty_clarification(direction):
    add_edge("a", "b", source_column="amount_paid", target_column="amount_paid")
    add_edge("b", "a", source_column="amount_paid", target_column="amount_paid")

    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="amount_paid", direction=direction), 1)

    assert result.error == "ambiguous"
    assert result.extra["candidates"] == ["a", "b"]


def test_column_cycle_without_direction_returns_all_real_candidates():
    add_edge("a", "b", source_column="amount_paid", target_column="amount_paid")
    add_edge("b", "a", source_column="amount_paid", target_column="amount_paid")

    result = resolve.resolve_table("amount_paid", database_id=1)

    assert result.status == "ambiguous"
    assert result.candidates == ["a", "b"]


def test_pending_columns_are_available_for_resolution_and_column_suggestions():
    review_service.add_pending(
        1,
        [
            LineageEdge(
                source_table="raw.invoices",
                source_column="amount_paid",
                target_table="stg.invoices",
                target_column="amount_paid",
                confidence=0.5,
                source_type="llm",
            )
        ],
    )

    result = TRAVERSE_CAPABILITY.run(
        TraverseParams(table="raw.invoices", column="missing_column", direction="downstream"), 1
    )

    assert result.error == "column_not_found"
    assert result.extra["candidates"] == ["amount_paid"]


def test_breaking_changes_matches_transitive_traverse_scope_and_dropped_sources(monkeypatch):
    from datetime import UTC, datetime

    from src.services.storage_service import BreakingChangeAlertRecord

    rename = BreakingChangeAlertRecord(
        id=1, database_id=1, kind="rename", table_name="a", new_name="a_v2", downstream_tables=["b"],
        suggested_action="Update reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    drop = BreakingChangeAlertRecord(
        id=2, database_id=1, kind="drop", table_name="removed", new_name=None, downstream_tables=["b"],
        suggested_action="Restore reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [rename, drop],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["c", "b", "a_v2"]), 1)

    assert result.extra["breaking_changes"] == [rename, drop]
    assert result.extra["checked_tables"] == ["c", "b", "a_v2"]


def test_breaking_changes_preserves_old_name_matching_and_scope_visibility(monkeypatch):
    from datetime import UTC, datetime

    from src.services.storage_service import BreakingChangeAlertRecord

    alert = BreakingChangeAlertRecord(
        id=1, database_id=1, kind="rename", table_name="a", new_name="a_v2", downstream_tables=["b"],
        suggested_action="Update reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [alert],
    )

    old_name = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["A"]), 1)
    unrelated = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["other"]), 1)
    all_alerts = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    assert old_name.extra["breaking_changes"] == [alert]
    assert unrelated.extra["breaking_changes"] == []
    assert unrelated.extra["checked_tables"] == ["other"]
    assert all_alerts.extra["checked_tables"] is None


def test_breaking_changes_adds_direct_repair_refs_and_transitive_downstreams(monkeypatch):
    from datetime import UTC, datetime

    alert = storage_service.BreakingChangeAlertRecord(
        id=1, database_id=1, kind="drop", table_name="department_revenue", new_name=None,
        downstream_tables=["revenue_alerts_staging", "revenue_alerts_final"],
        suggested_action="Restore reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    add_edge(
        "other_source",
        "revenue_alerts_staging",
        evidence=LineageEvidence(
            file_path="models/marts/revenue_alerts_staging.sql",
            line_range=[1, 1],
            raw_sql="SELECT *\nFROM {{ ref('department_revenue') }}\n",
        ),
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [alert],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    assert result.extra["breaking_change_repair_guidance"] == {
        1: {
            "direct_refs": [{
                "table": "revenue_alerts_staging",
                "file": "models/marts/revenue_alerts_staging.sql",
                "stored_sql_line": 2,
                "sql_line": "FROM {{ ref('department_revenue') }}",
            }],
            "transitive_refs": ["revenue_alerts_final"],
        }
    }


def test_breaking_change_repair_refs_require_a_complete_identifier(monkeypatch):
    from datetime import UTC, datetime

    alert = storage_service.BreakingChangeAlertRecord(
        id=1, database_id=1, kind="drop", table_name="department_revenue", new_name=None,
        downstream_tables=["revenue_alerts_staging"], suggested_action="Restore reference.",
        detected_at=datetime.now(UTC), acknowledged=False,
    )
    add_edge(
        "other_source", "revenue_alerts_staging",
        evidence=LineageEvidence(file_path="model.sql", line_range=[9, 9], raw_sql="FROM department_revenue_v2"),
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [alert],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    assert result.extra["breaking_change_repair_guidance"][1] == {
        "direct_refs": [], "transitive_refs": ["revenue_alerts_staging"]
    }


def test_breaking_change_repair_refs_use_stored_sql_line_not_evidence_range(monkeypatch):
    from datetime import UTC, datetime

    alert = storage_service.BreakingChangeAlertRecord(
        id=1, database_id=1, kind="rename", table_name="old_table", new_name="new_table",
        downstream_tables=["consumer"], suggested_action="Update reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    add_edge(
        "source", "consumer",
        evidence=LineageEvidence(file_path="consumer.sql", line_range=[99, 99], raw_sql="SELECT 1\nJOIN old_table"),
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [alert],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    direct_ref = result.extra["breaking_change_repair_guidance"][1]["direct_refs"][0]
    assert direct_ref["stored_sql_line"] == 2
    assert 99 not in direct_ref.values()


def test_breaking_change_repair_refs_fall_back_when_no_stored_sql_matches(monkeypatch):
    from datetime import UTC, datetime

    alert = storage_service.BreakingChangeAlertRecord(
        id=1, database_id=1, kind="drop", table_name="gone", new_name=None,
        downstream_tables=["consumer"], suggested_action="Restore reference.", detected_at=datetime.now(UTC), acknowledged=False,
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [alert],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    assert result.extra["breaking_change_repair_guidance"][1] == {
        "direct_refs": [], "transitive_refs": ["consumer"]
    }


def test_get_asset_excludes_stale_relationship_fields_and_vocabulary(monkeypatch):
    add_edge("raw.orders", "mart.orders")
    profile = storage_service.NodeProfile(
        node_id=1,
        current_name="mart.orders",
        defined_in="models/mart/orders.sql",
        columns_produced=["order_id"],
        columns_consumed=["raw_id"],
        upstream_tables=["raw.orders"],
        downstream_tables=["stale.orders"],
        source_types=["parser"],
        transform_types=["direct"],
        confidence_min=1.0,
        confidence_max=1.0,
        dropped_at=None,
        first_seen=None,
        last_modified=None,
        modified_count=1,
        previous_names=[],
    )
    monkeypatch.setattr(storage_service, "all_node_names", lambda _database_id: ["mart.orders"])
    monkeypatch.setattr(storage_service, "load_asset_profiles", lambda _database_id, _names: {"mart.orders": profile})

    result = GET_ASSET_CAPABILITY.run(GetAssetParams(tables=["mart.orders"]), 1)
    asset = result.extra["assets"][0]

    assert {"upstream_tables", "downstream_tables", "upstream_count", "downstream_count"}.isdisjoint(
        asset.model_dump()
    )
    assert GET_ASSET_CAPABILITY.vocabulary(result) == {"mart.orders", "order_id", "raw_id"}


def test_assess_change_value_gives_different_note_than_type():
    add_edge("ecom.orders", "stg.orders", transform_type="aggregation")
    type_result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="type"), 1)
    value_result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="value"), 1)
    (edge,) = type_result.confirmed
    assert (
        type_result.extra["risk_by_edge"][edge_fingerprint(edge)]
        != value_result.extra["risk_by_edge"][edge_fingerprint(edge)]
    )


def test_assess_change_drop_gives_more_severe_note_than_rename():
    add_edge("ecom.orders", "stg.orders", transform_type="join")
    drop_result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="drop"), 1)
    rename_result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="rename"), 1)
    (edge,) = drop_result.confirmed
    drop_note = drop_result.extra["risk_by_edge"][edge_fingerprint(edge)]
    rename_note = rename_result.extra["risk_by_edge"][edge_fingerprint(edge)]
    assert "nghiêm trọng" in drop_note
    assert drop_note != rename_note


def test_assess_change_covers_confirmed_and_pending_edges():
    add_edge("ecom.orders", "stg.orders", transform_type="direct")
    review_service.add_pending(1,
        [LineageEdge(source_table="stg.orders", target_table="legacy.orders", confidence=0.5, source_type="llm")]
    )
    result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="ecom.orders", change_kind="value"), 1)
    edges = [*result.confirmed, *result.pending]
    assert len(edges) == 2
    assert all(edge_fingerprint(edge) in result.extra["risk_by_edge"] for edge in edges)


def test_template_is_grounded_against_capability_vocabulary():
    add_edge("ecom.orders", "stg.orders")
    result = TRAVERSE_CAPABILITY.run(TraverseParams(table="ecom.orders", direction="downstream"), 1)
    facts = {"confirmed": [], "inferred_pending": []}
    assert (
        guard.unknown_mentions(TRAVERSE_CAPABILITY.template(result), facts, TRAVERSE_CAPABILITY.vocabulary(result))
        == []
    )


@pytest.mark.parametrize(
    "params,phrase",
    [
        (TraverseParams(table="orders", direction="downstream"), "ecom.orders, stg.orders"),
        (TraverseParams(table="customerz", direction="downstream"), "raw.customers"),
    ],
)
def test_error_vocabulary_keeps_clarification_and_suggestions_grounded(params, phrase):
    add_edge("ecom.orders", "stg.orders")
    add_edge("raw.customers", "stg_customers")
    result = TRAVERSE_CAPABILITY.run(params, 1)
    assert (
        guard.unknown_mentions(
            phrase, {"confirmed": [], "inferred_pending": []}, TRAVERSE_CAPABILITY.vocabulary(result)
        )
        == []
    )


def test_registry_registers_core_capabilities_and_builds_schemas(monkeypatch):
    assert "traverse" in REGISTRY
    assert {"downstream", "upstream"}.isdisjoint(REGISTRY)
    assert {tool.name for tool in build_tools()} == set(REGISTRY)

    class FakeParams(BaseModel):
        table: str

    class FakeCapability:
        name = "fake"
        description = "Test-only capability."
        Params = FakeParams

        def run(self, params: BaseModel, database_id: int) -> CapabilityResult:
            return CapabilityResult(extra={"resolved_table": params.table})

        def vocabulary(self, result: CapabilityResult) -> set[str]:
            return set()

        def prompt_rules(self) -> str:
            return "Fake rule."

        def template(self, result: CapabilityResult) -> str:
            return "Fake"

    monkeypatch.setitem(REGISTRY, "fake", FakeCapability())
    assert {tool.name for tool in build_tools()} == set(REGISTRY)
    assert "Fake rule." in merged_prompt_rules()


def test_analyze_query_returns_only_resolved_sources_in_vocabulary():
    add_edge("raw.invoices", "stg.invoices", source_column="amount_paid", target_column="amount_paid")

    result = ANALYZE_QUERY_CAPABILITY.run(
        AnalyzeQueryParams(sql="SELECT amount_paid AS total_revenue FROM stg.invoices"), 1
    )

    assert result.error is None
    assert result.extra["query_columns"] == [
        {
            "output_column": "total_revenue",
            "source_table": "stg.invoices",
            "source_column": "amount_paid",
            "resolved": True,
        }
    ]
    assert ANALYZE_QUERY_CAPABILITY.vocabulary(result) == {"stg.invoices", "amount_paid"}


def test_analyze_query_keeps_unknown_sources_out_of_vocabulary_and_distinguishes_parse_outcomes():
    unknown = ANALYZE_QUERY_CAPABILITY.run(AnalyzeQueryParams(sql="SELECT id FROM missing_table"), 1)
    constant = ANALYZE_QUERY_CAPABILITY.run(AnalyzeQueryParams(sql="SELECT 1 AS one"), 1)
    invalid = ANALYZE_QUERY_CAPABILITY.run(AnalyzeQueryParams(sql="THIS IS NOT VALID SQL (((;"), 1)

    assert unknown.extra["query_columns"][0]["resolved"] is False
    assert ANALYZE_QUERY_CAPABILITY.vocabulary(unknown) == set()
    assert constant.error is None and constant.extra == {
        "query_columns": [],
        "note": "Parser không trích được cạnh nào (có thể SQL không có SELECT/JOIN rõ ràng)",
    }
    assert invalid.error == "sql_parse_failed"
    assert invalid.extra["reason"] == "The query could not be parsed."
    assert "THIS IS NOT VALID SQL" not in str(invalid.extra)
