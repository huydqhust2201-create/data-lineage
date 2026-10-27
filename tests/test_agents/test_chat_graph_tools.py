import networkx as nx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import graph as agent_graph
from src.agents.chat import guard
from src.agents.chat.base import edge_fingerprint
from src.agents.chat.registry import REGISTRY, build_tools, merged_prompt_rules
from src.agents.nodes import query_nodes
from src.agents.tools.asset_tools import GET_ASSET_CAPABILITY
from src.agents.tools.breaking_change_tools import BREAKING_CHANGES_CAPABILITY, BreakingChangesParams
from src.agents.tools.ddl_preview_tools import PreviewDdlImpactParams
from src.agents.tools.description_tools import SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY
from src.agents.tools.graph_tools import (
    LIST_RELATIONSHIPS_CAPABILITY,
    SEARCH_TABLES_CAPABILITY,
    ListRelationshipsParams,
    SearchTablesParams,
)
from src.agents.tools.impact_tools import (
    _CHANGE_KIND_PROMPT_RULE,
    ASSESS_CHANGE_CAPABILITY,
    TRAVERSE_CAPABILITY,
    AssessChangeParams,
    TraverseParams,
)
from src.config import get_settings
from src.models.schemas import LineageEdge
from src.services import graph_service, impact_service, review_service


@pytest.fixture(autouse=True)
def fresh_lineage():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(1, None)
    review_service._reset()


@pytest.fixture
def chat_settings(monkeypatch):
    def apply(**overrides):
        for key, value in overrides.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()

    get_settings.cache_clear()
    yield apply
    monkeypatch.undo()
    get_settings.cache_clear()


def add_edge(source, target, *, source_type="parser"):
    edge = LineageEdge(
        source_table=source,
        target_table=target,
        confidence=0.5 if source_type == "llm" else 1.0,
        source_type=source_type,
    )
    if source_type == "llm":
        review_service.add_pending(1, [edge])
    else:
        graph_service.add_edge(1, edge)


def tool_call(call_id, name, **args):
    if name in {"upstream", "downstream"}:
        args["direction"] = name
        name = "traverse"
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    def invoke(self, _messages):
        return next(self.responses)


def test_search_without_query_returns_only_known_tables(chat_settings):
    chat_settings(CHAT_SEARCH_LIMIT=2)
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "fct.sales")
    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(), 1)
    assert result.extra["tables"] == ["fct.sales", "raw.orders"]
    assert result.extra["truncated"] is True
    assert set(result.extra["tables"]) <= {"raw.orders", "stg.orders", "fct.sales"}


def test_search_filters_pending_only_table():
    add_edge("stg.orders", "legacy_ltv", source_type="llm")
    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(query="ltv"), 1)
    assert result.extra["tables"] == ["legacy_ltv"]


def test_search_with_query_on_empty_graph_does_not_crash():
    """Regression: get_close_matches(n=0) từng ném ValueError khi đồ thị
    trống (0 bảng đã biết) và câu hỏi có kèm query — 500 lỗi thật đã xảy ra
    khi user hỏi trên 1 đồ thị vừa bị xoá/chưa từng ingest."""
    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(query="orders"), 1)
    assert result.error == "table_not_found"
    assert result.extra["suggestions"] == []


def test_search_returns_column_error_instead_of_guessing_a_table():
    graph_service.add_edge(
        1,
        LineageEdge(
            source_table="raw.invoices",
            source_column="amount_paid",
            target_table="stg.invoices",
            target_column="amount_paid",
            confidence=1.0,
            source_type="parser",
        ),
    )

    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(query="amount_paid"), 1)

    assert result.error == "is_a_column"
    assert result.extra == {"column_mention": "amount_paid"}


def test_search_requires_user_selection_for_multiple_direct_table_matches():
    add_edge("raw.orders", "stg.orders")

    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(query="orders"), 1)

    assert result.error == "needs_selection"
    assert result.extra["candidates"] == ["raw.orders", "stg.orders"]


def test_agent_can_retry_a_column_search_with_traverse(monkeypatch):
    graph_service.add_edge(
        1,
        LineageEdge(
            source_table="raw.invoices",
            source_column="amount_paid",
            target_table="stg.invoices",
            target_column="amount_paid",
            confidence=1.0,
            source_type="parser",
        ),
    )
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="amount_paid")]),
            AIMessage(content="", tool_calls=[tool_call("trace", "traverse", table="amount_paid", direction="downstream")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="raw.invoices affects stg.invoices")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)

    result = agent_graph.build_chat_graph().invoke(
        {"question": "trace amount_paid", "database_id": 1, "messages": [HumanMessage(content="trace amount_paid")]}
    )

    assert [step["error"] for step in result["steps"]] == ["is_a_column", None]
    assert result["steps"][1]["resolved"]["table"] == "raw.invoices"


def test_search_clamps_llm_limit(chat_settings):
    chat_settings(CHAT_SEARCH_LIMIT=2)
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "fct.sales")
    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(limit=9999), 1)
    assert len(result.extra["tables"]) == 2
    assert result.extra["total"] == 3
    assert result.extra["truncated"] is True


def test_search_vocabulary_does_not_allow_unreturned_tables(chat_settings):
    chat_settings(CHAT_SEARCH_LIMIT=2)
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "mart.sales")
    result = SEARCH_TABLES_CAPABILITY.run(SearchTablesParams(), 1)
    assert guard.unknown_mentions("stg.orders", {}, SEARCH_TABLES_CAPABILITY.vocabulary(result)) == ["stg.orders"]


def test_list_relationships_defaults_to_pending_only():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "legacy_ltv", source_type="llm")
    result = LIST_RELATIONSHIPS_CAPABILITY.run(ListRelationshipsParams(), 1)
    assert [(e.source_table, e.target_table) for e in result.pending] == [("stg.orders", "legacy_ltv")]
    assert result.confirmed == []
    assert result.extra["total_confirmed"] == 0
    assert result.extra["total_pending"] == 1


def test_list_relationships_status_confirmed_excludes_pending():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "legacy_ltv", source_type="llm")
    result = LIST_RELATIONSHIPS_CAPABILITY.run(ListRelationshipsParams(status="confirmed"), 1)
    assert [(e.source_table, e.target_table) for e in result.confirmed] == [("raw.orders", "stg.orders")]
    assert result.pending == []


def test_list_relationships_status_all_includes_both():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "legacy_ltv", source_type="llm")
    result = LIST_RELATIONSHIPS_CAPABILITY.run(ListRelationshipsParams(status="all"), 1)
    assert len(result.confirmed) == 1
    assert len(result.pending) == 1


def test_list_relationships_clamps_to_configured_limit(chat_settings):
    chat_settings(CHAT_SEARCH_LIMIT=1)
    add_edge("raw.orders", "stg.orders", source_type="llm")
    add_edge("stg.orders", "fct.sales", source_type="llm")
    result = LIST_RELATIONSHIPS_CAPABILITY.run(ListRelationshipsParams(status="pending", limit=9999), 1)
    assert len(result.pending) == 1
    assert result.extra["total_pending"] == 2
    assert result.extra["truncated"] is True


def test_agent_answers_unscoped_pending_question_via_list_relationships(monkeypatch):
    add_edge("stg.orders", "legacy_ltv", source_type="llm")
    agent_llm = FakeLLM(
        [
            AIMessage(
                content="", tool_calls=[tool_call("list", "list_relationships", status="pending")]
            ),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="1 quan hệ đang chờ duyệt: stg.orders -> legacy_ltv")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)
    result = agent_graph.build_chat_graph().invoke(
        {"question": "what is pending?", "database_id": 1, "messages": [HumanMessage(content="what is pending?")]}
    )
    assert len(result["pending"]) == 1
    assert result["pending"][0].target_table == "legacy_ltv"
    assert result["answer"]


def test_registry_registers_search_schema():
    assert set(REGISTRY) == {
        "traverse",
        "assess_change",
        "search_tables",
        "list_relationships",
        "search_by_description",
        "search_column_description",
        "preview_ddl_impact",
        "breaking_changes",
        "analyze_query",
    }
    assert {tool.name for tool in build_tools()} == set(REGISTRY)


def test_assess_change_owns_change_kind_and_preserves_preview_ddl_schema():
    assert "change_kind" not in TraverseParams.model_fields
    assert set(AssessChangeParams.model_fields) == {"table", "column", "change_kind"}
    assert set(PreviewDdlImpactParams.model_fields) == {"sql", "dialect"}
    assert len(REGISTRY["traverse"].prompt_rules()) < 220


def test_traverse_uses_configured_default_depth(monkeypatch, chat_settings):
    add_edge("raw.orders", "stg.orders")
    calls = []
    chat_settings(CHAT_DEFAULT_TRAVERSE_DEPTH=2)
    monkeypatch.setattr(
        impact_service,
        "query_impact_edges",
        lambda _database_id, _table, _column, _direction, depth: calls.append(depth) or ([], []),
    )

    TRAVERSE_CAPABILITY.run(TraverseParams(table="raw.orders", direction="downstream"), 1)

    assert calls == [2]


def test_traverse_explicit_depth_overrides_default(monkeypatch, chat_settings):
    add_edge("raw.orders", "stg.orders")
    calls = []
    chat_settings(CHAT_DEFAULT_TRAVERSE_DEPTH=2)
    monkeypatch.setattr(
        impact_service,
        "query_impact_edges",
        lambda _database_id, _table, _column, _direction, depth: calls.append(depth) or ([], []),
    )

    TRAVERSE_CAPABILITY.run(TraverseParams(table="raw.orders", direction="downstream", depth=5), 1)

    assert calls == [5]
    assert len(REGISTRY) == 9
    assert "assess_change" in REGISTRY


def test_change_kind_prompt_rule_is_emitted_only_by_assess_change():
    capabilities = list(REGISTRY.values())
    assert sum(_CHANGE_KIND_PROMPT_RULE in capability.prompt_rules() for capability in capabilities) == 1
    assert _CHANGE_KIND_PROMPT_RULE in REGISTRY["assess_change"].prompt_rules()
    for change_kind in ("type", "value", "drop", "rename", "drop_table", "rename_table"):
        assert f"'{change_kind}'" in _CHANGE_KIND_PROMPT_RULE


def test_prompt_rules_state_each_tool_trigger_and_stay_within_the_prompt_budget():
    assert "what breaks" in ASSESS_CHANGE_CAPABILITY.prompt_rules()
    assert "where data comes from" in REGISTRY["traverse"].prompt_rules()
    assert "without naming the column" in SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.prompt_rules()
    assert "specific column" not in SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY.description
    assert len(merged_prompt_rules()) < 2600


def test_assess_change_returns_the_shared_downstream_risk():
    edge = LineageEdge(
        source_table="raw.orders", target_table="stg.orders", transform_type="join", confidence=1.0, source_type="parser"
    )
    graph_service.add_edge(1, edge)

    result = ASSESS_CHANGE_CAPABILITY.run(AssessChangeParams(table="raw.orders", change_kind="type"), 1)

    (confirmed,) = result.confirmed
    assert result.extra["risk_by_edge"][edge_fingerprint(confirmed)] == impact_service.risk_note("join", "type")


def test_breaking_changes_filters_alerts_by_the_supplied_table_set(monkeypatch):
    from datetime import UTC, datetime

    from src.services.storage_service import BreakingChangeAlertRecord

    calls = []
    rename = BreakingChangeAlertRecord(
        id=1, database_id=7, kind="rename", table_name="raw.invoices", new_name="raw.invoices_v2",
        downstream_tables=["department_revenue"], suggested_action="Update reference.",
        detected_at=datetime.now(UTC), acknowledged=False,
    )
    drop = BreakingChangeAlertRecord(
        id=2, database_id=7, kind="drop", table_name="legacy.invoices", new_name=None,
        downstream_tables=["department_revenue"], suggested_action="Restore reference.",
        detected_at=datetime.now(UTC), acknowledged=False,
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda database_id, include_acknowledged: calls.append((database_id, include_acknowledged)) or [rename, drop],
    )

    result = BREAKING_CHANGES_CAPABILITY.run(
        BreakingChangesParams(tables=["report", "department_revenue", "raw.invoices_v2"]), 7
    )

    assert calls == [(7, True)]
    assert result.extra["breaking_changes"] == [rename, drop]
    assert result.extra["checked_tables"] == ["report", "department_revenue", "raw.invoices_v2"]


def test_breaking_changes_matches_dropped_and_old_table_names_without_graph_lookup(monkeypatch):
    from datetime import UTC, datetime

    from src.services.storage_service import BreakingChangeAlertRecord

    rename = BreakingChangeAlertRecord(
        id=1, database_id=1, kind="rename", table_name="raw.invoices", new_name="raw.invoices_v2",
        downstream_tables=["department_revenue"], suggested_action="Update reference.",
        detected_at=datetime.now(UTC), acknowledged=False,
    )
    drop = BreakingChangeAlertRecord(
        id=2, database_id=1, kind="drop", table_name="legacy.invoices", new_name=None,
        downstream_tables=["department_revenue"], suggested_action="Restore reference.",
        detected_at=datetime.now(UTC), acknowledged=False,
    )
    monkeypatch.setattr(
        "src.agents.tools.breaking_change_tools.storage_service.list_breaking_change_alerts",
        lambda *_args, **_kwargs: [rename, drop],
    )

    old_name = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["RAW.INVOICES"]), 1)
    drop_downstream = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["department_revenue"]), 1)
    unrelated = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(tables=["unrelated"]), 1)
    all_alerts = BREAKING_CHANGES_CAPABILITY.run(BreakingChangesParams(), 1)

    assert old_name.extra["breaking_changes"] == [rename]
    assert drop_downstream.extra["breaking_changes"] == [rename, drop]
    assert unrelated.extra["breaking_changes"] == []
    assert unrelated.extra["checked_tables"] == ["unrelated"]
    assert all_alerts.extra["breaking_changes"] == [rename, drop]
    assert all_alerts.extra["checked_tables"] is None


def test_breaking_changes_prompt_rules_prioritize_it_before_lineage_investigation():
    rules = BREAKING_CHANGES_CAPABILITY.prompt_rules()

    assert "BEFORE investigating lineage" in rules
    assert "Only look elsewhere" in rules
    assert len(merged_prompt_rules()) < 2600


def test_get_asset_description_mentions_renamed_and_dropped_assets():
    description = GET_ASSET_CAPABILITY.description.lower()
    assert "renamed" in description
    assert "dropped" in description


def test_agent_stops_for_user_selection_when_search_matches_multiple_tables(monkeypatch):
    add_edge("ecom.orders", "stg.orders")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="order")]),
            AIMessage(content="", tool_calls=[tool_call("downstream", "traverse", table="ecom.orders", direction="downstream")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="ecom.orders affects stg.orders")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)
    result = agent_graph.build_chat_graph().invoke(
        {"question": "impact orders", "database_id": 1, "messages": [HumanMessage(content="impact orders")]}
    )
    assert len(result["steps"]) == 1
    assert result["steps"][0]["error"] == "needs_selection"
    assert result["clarification"]["candidates"] == ["ecom.orders", "stg.orders"]


def test_agent_can_answer_after_only_search(monkeypatch):
    add_edge("ecom.orders", "stg.orders")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="order")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="Available: ecom.orders")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)
    result = agent_graph.build_chat_graph().invoke(
        {"question": "find orders", "database_id": 1, "messages": [HumanMessage(content="find orders")]}
    )
    assert result["steps"][0]["resolved"] is None
    assert result["confirmed"] == []
    assert result["answer"]
