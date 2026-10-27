import json

import networkx as nx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents import graph as agent_graph
from src.agents.chat.base import CapabilityResult, edge_fingerprint
from src.agents.nodes import query_nodes
from src.agents.tools.asset_tools import GetAssetParams
from src.agents.tools.breaking_change_tools import BreakingChangesParams
from src.config import get_settings
from src.models.schemas import AssetProfile, LineageEdge, LineageEvidence
from src.services import chat_service, graph_service, review_service


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
        return get_settings()

    get_settings.cache_clear()
    yield apply
    monkeypatch.undo()
    get_settings.cache_clear()


def add_edge(source, target):
    graph_service.add_edge(1, LineageEdge(source_table=source, target_table=target, confidence=1.0, source_type="parser"))


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

    def stream(self, messages):
        yield self.invoke(messages)


class CapturingLLM(FakeLLM):
    def __init__(self, responses):
        super().__init__(responses)
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return super().invoke(messages)


class FakeAssetCapability:
    name = "get_asset"
    description = "test asset capability"
    Params = GetAssetParams

    def __init__(self, *, max_assets=None):
        self.calls = []
        self.max_assets = max_assets

    def run(self, params, database_id: int):
        self.calls.append((list(params.tables), database_id))
        tables = params.tables if self.max_assets is None else params.tables[: self.max_assets]
        assets = [
            AssetProfile(
                name=table,
                defined_in=f"models/{table}.sql",
                is_defined=True,
                columns_produced=["order_id"],
                columns_consumed=["raw_id"],
                upstream_tables=["raw.orders"],
                downstream_tables=["mart.orders"],
                upstream_count=1,
                downstream_count=1,
                source_types=["parser"],
                confidence_min=1.0,
                confidence_max=1.0,
                transform_types=["direct"],
                last_modified="2026-08-10T00:00:00+00:00",
                first_seen="2026-08-10T00:00:00+00:00",
                modified_count=1,
                previous_names=[{"name": "old_orders", "changed_at": "2026-08-09T00:00:00+00:00"}],
                is_dropped=False,
                pending_count=0,
            )
            for table in tables
        ]
        return CapabilityResult(extra={"assets": assets, "skipped": [], "truncated": len(tables) < len(params.tables)})

    def vocabulary(self, result):
        return {"old_orders", "order_id", *(asset.name for asset in result.extra["assets"])}

    def prompt_rules(self):
        return "test"

    def template(self, result):
        return "test"


class FakeBreakingChangesCapability:
    name = "breaking_changes"
    description = "test breaking changes capability"
    Params = BreakingChangesParams

    def __init__(self, alerts=None, error=None):
        self.alerts = alerts or []
        self.error = error
        self.calls = []

    def run(self, params, database_id: int):
        self.calls.append((params.tables, database_id))
        return CapabilityResult(error=self.error, extra={"breaking_changes": self.alerts, "checked_tables": params.tables})

    def vocabulary(self, result):
        return set()

    def prompt_rules(self):
        return "test"

    def template(self, result):
        return "test"


def test_graph_runs_one_tool_and_records_step(monkeypatch):
    add_edge("raw.orders", "stg.orders")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="done"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="confirmed raw.orders")])
    monkeypatch.setattr(
        query_nodes,
        "get_llm",
        lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm,
    )
    result = agent_graph.build_chat_graph().invoke({"question": "impact", "database_id": 1, "messages": [HumanMessage(content="impact")]})
    assert len(result["steps"]) == 1
    assert result["steps"][0]["tool"] == "traverse"
    assert result["steps"][0]["agent_step"] == 1
    assert result["steps"][0]["duration_ms"] >= 0
    assert [edge.target_table for edge in result["confirmed"]] == ["stg.orders"]


def test_tools_node_records_exact_duration_and_the_current_agent_step(monkeypatch):
    add_edge("raw.orders", "stg.orders")
    clock = iter([10.0, 10.125])
    monkeypatch.setattr(query_nodes, "_monotonic", lambda: next(clock))

    update = query_nodes.tools_node(
        {
            "question": "impact",
            "database_id": 1,
            "agent_steps_used": 3,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")])],
        }
    )

    assert update["steps"][0]["duration_ms"] == 125
    assert update["steps"][0]["agent_step"] == 3


def test_stop_reason_prioritizes_clarification_over_exhausted_budget(chat_settings):
    chat_settings(CHAT_MAX_TOOL_CALLS=1)
    assert chat_service._stop_reason({"clarification": {}, "tool_calls_used": 1}) == "clarification"


def test_stop_reason_detects_both_budgets_and_a_normal_final_agent_turn(chat_settings):
    chat_settings(CHAT_MAX_TOOL_CALLS=2, CHAT_MAX_AGENT_STEPS=2)
    assert chat_service._stop_reason({"tool_calls_used": 2}) == "budget_exhausted"
    assert (
        chat_service._stop_reason(
            {
                "agent_steps_used": 2,
                "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orders")])],
            }
        )
        == "budget_exhausted"
    )
    assert chat_service._stop_reason({"agent_steps_used": 2, "messages": [AIMessage(content="DONE")]}) == "completed"
    assert chat_service._stop_reason({"steps": [{"error": "table_not_found"}]}) == "completed"


def test_graph_merges_overlapping_tool_results_by_stable_fingerprint(monkeypatch):
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "fct_sales")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="", tool_calls=[tool_call("two", "downstream", table="stg.orders")]),
            AIMessage(content="done"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="confirmed")])
    monkeypatch.setattr(
        query_nodes,
        "get_llm",
        lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm,
    )
    result = agent_graph.build_chat_graph().invoke({"question": "impact", "database_id": 1, "messages": [HumanMessage(content="impact")]})
    assert len(result["steps"]) == 2
    assert [step["agent_step"] for step in result["steps"]] == [1, 2]
    assert [(edge.source_table, edge.target_table) for edge in result["confirmed"]] == [
        ("raw.orders", "stg.orders"),
        ("stg.orders", "fct_sales"),
    ]


def test_graph_dedupes_cross_direction_results_and_merges_hops(monkeypatch):
    add_edge("raw.orders", "stg.orders")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="", tool_calls=[tool_call("two", "upstream", table="stg.orders")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="confirmed")])
    monkeypatch.setattr(
        query_nodes,
        "get_llm",
        lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm,
    )
    result = agent_graph.build_chat_graph().invoke({"question": "impact", "database_id": 1, "messages": [HumanMessage(content="impact")]})
    assert len(result["confirmed"]) == 1
    fingerprint = edge_fingerprint(result["confirmed"][0])
    assert result["hops"][fingerprint] == 1
    facts = query_nodes._facts(result)
    assert facts["confirmed"][0]["hops"] == 1
    assert fingerprint not in facts


def test_tools_node_does_not_attach_change_kind_risk_to_traverse():
    graph_service.add_edge(1,
        LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser", transform_type="join")
    )
    update = query_nodes.tools_node(
        {
            "question": "đổi kiểu dữ liệu cột join thì sao", "database_id": 1,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[tool_call("one", "downstream", table="raw.orders", change_kind="type")],
                )
            ],
        }
    )
    assert len(update["confirmed"]) == 1
    assert "risk" not in update


def test_leaf_table_is_ok_when_the_graph_has_other_lineage():
    add_edge("raw.orders", "stg.orders")
    add_edge("stg.orders", "fct_sales")
    update = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="fct_sales")])],
        }
    )
    facts = query_nodes._facts({**update, "database_id": 1})
    assert facts["graph_is_empty"] is False
    assert facts["confirmed"] == []


def test_empty_graph_takes_priority_over_table_not_found():
    update = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orders")])],
        }
    )
    assert query_nodes._facts({**update, "database_id": 1})["graph_is_empty"] is True


def test_tools_node_stops_batch_at_budget_and_preserves_all_call_ids(chat_settings):
    add_edge("raw.orders", "stg.orders")
    chat_settings(CHAT_MAX_TOOL_CALLS=1)
    calls = [
        tool_call("one", "downstream", table="raw.orders"),
        tool_call("two", "downstream", table="raw.orders"),
        tool_call("three", "unknown"),
    ]
    update = query_nodes.tools_node(
        {"question": "impact", "database_id": 1, "agent_steps_used": 1, "messages": [AIMessage(content="", tool_calls=calls)]}
    )
    messages = update["messages"]
    assert update["tool_calls_used"] == 1
    assert [message.tool_call_id for message in messages] == ["one", "two", "three"]
    assert all(isinstance(message, ToolMessage) for message in messages)
    assert "budget_exhausted" in update["warnings"]


def test_ambiguous_tool_stops_batch_and_routes_to_compose():
    add_edge("ecom.orders", "stg.orders")
    calls = [
        tool_call("one", "downstream", table="orders"),
        tool_call("two", "downstream", table="ecom.orders"),
    ]
    update = query_nodes.tools_node(
        {"question": "impact", "database_id": 1, "agent_steps_used": 1, "messages": [AIMessage(content="", tool_calls=calls)]}
    )
    state = {
        "question": "impact", "database_id": 1,
        "messages": [AIMessage(content="", tool_calls=calls), *update["messages"]],
        **update,
    }
    assert [message.tool_call_id for message in update["messages"]] == ["one", "two"]
    assert update["clarification"]["candidates"] == ["ecom.orders", "stg.orders"]
    assert query_nodes.route_after_tools(state) == "compose"


def test_ambiguous_summary_does_not_expose_candidates():
    content = query_nodes._summary(
        CapabilityResult(error="ambiguous", extra={"candidates": ["ecom.orders", "stg.orders"]})
    )
    assert content == '{"ok": false, "error": "ambiguous"}'
    assert "candidates" not in content
    assert "ecom.orders" not in content


def test_summary_lists_far_tables_and_marks_truncation(chat_settings):
    chat_settings(CHAT_MAX_EDGES=1)
    result = CapabilityResult(
        confirmed=[
            LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser"),
            LineageEdge(source_table="raw.orders", target_table="fct.sales", confidence=1.0, source_type="parser"),
        ],
        extra={"resolved_table": "raw.orders", "resolved_column": None, "direction": "downstream"},
    )
    summary = query_nodes._summary(result)
    assert json.loads(summary)["confirmed"] == {"count": 2, "tables": ["stg.orders"]}
    assert json.loads(summary)["tables_truncated"] is True


@pytest.mark.parametrize(
    "call,warning",
    [
        (tool_call("unknown", "not_registered"), "unknown_tool: not_registered"),
        (tool_call("invalid", "downstream"), "invalid_tool_args: traverse"),
    ],
)
def test_invalid_tool_calls_return_tool_messages_without_using_budget(call, warning):
    update = query_nodes.tools_node({"question": "impact", "database_id": 1, "messages": [AIMessage(content="", tool_calls=[call])]})
    assert update["tool_calls_used"] == 0
    assert update["messages"][0].tool_call_id == call["id"]
    assert warning in update["warnings"]


def test_steps_record_each_tool_error_and_raw_args():
    add_edge("ecom.orders", "stg.orders")
    calls = [
        tool_call("unknown", "not_registered", table="ignored"),
        tool_call("invalid", "downstream"),
        tool_call("ambiguous", "downstream", table="orders"),
        tool_call("skipped", "downstream", table="ecom.orders"),
    ]
    update = query_nodes.tools_node({"question": "impact", "database_id": 1, "messages": [AIMessage(content="", tool_calls=calls)]})
    assert [step["error"] for step in update["steps"]] == [
        "unknown_tool",
        "invalid_args",
        "ambiguous",
        "not_executed",
    ]
    assert update["steps"][0]["args"] == {"table": "ignored"}

    not_found = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("missing", "downstream", table="orderz")])],
        }
    )
    assert not_found["steps"][0]["error"] == "table_not_found"


def test_multiple_tools_keep_independent_resolved_trace():
    add_edge("ecom.orders", "stg.orders")
    calls = [
        tool_call("downstream", "downstream", table="ecom.orders"),
        tool_call("upstream", "upstream", table="stg.orders"),
    ]
    update = query_nodes.tools_node(
        {"question": "impact", "database_id": 1, "agent_steps_used": 1, "messages": [AIMessage(content="", tool_calls=calls)]}
    )
    assert [step["resolved"] for step in update["steps"][:2]] == [
        {"table": "ecom.orders", "column": None, "direction": "downstream"},
        {"table": "stg.orders", "column": None, "direction": "upstream"},
    ]
    assert [step["tool"] for step in update["steps"]] == ["traverse", "traverse"]
    assert [step["agent_step"] for step in update["steps"]] == [1, 1]


def test_diagnostic_question_with_only_traverse_does_not_force_lifecycle_tools(monkeypatch):
    add_edge("raw.invoices", "stg.invoices")
    add_edge("stg.invoices", "department_revenue")
    breaking = FakeBreakingChangesCapability()
    assets = FakeAssetCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", assets)

    update = query_nodes.tools_node(
        {
            "question": "department_revenue bị lỗi, tại sao?",
            "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "upstream", table="department_revenue")])],
        }
    )

    assert [step["tool"] for step in update["steps"]] == ["traverse"]
    assert breaking.calls == []
    assert assets.calls == []
    assert query_nodes._facts({"database_id": 1, **update})["breaking_changes_checked"] is False
    assert query_nodes.route_after_tools({"database_id": 1, **update}) == "agent"


def test_agent_requested_breaking_changes_runs_in_its_original_batch_order(monkeypatch):
    add_edge("raw.invoices", "report")
    breaking = FakeBreakingChangesCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", FakeAssetCapability())
    calls = [
        tool_call("alert", "breaking_changes"),
        tool_call("upstream", "upstream", table="report"),
    ]

    update = query_nodes.tools_node(
        {"question": "report bị lỗi", "database_id": 1, "messages": [AIMessage(content="", tool_calls=calls)]}
    )

    assert [step["tool"] for step in update["steps"]] == ["breaking_changes", "traverse"]
    assert breaking.calls == [(None, 1)]
    assert [message.tool_call_id for message in update["messages"]] == ["alert", "upstream"]
    assert query_nodes._facts({"database_id": 1, **update})["breaking_changes_checked"] is True


def test_chat_state_has_no_forced_triage_fields():
    assert {"lifecycle_status", "triage_assets_truncated", "triage_asset_coverage"}.isdisjoint(
        query_nodes.ChatAgentState.__annotations__
    )


def test_requested_breaking_changes_respects_the_normal_tool_budget(monkeypatch, chat_settings):
    chat_settings(CHAT_MAX_TOOL_CALLS=1)
    add_edge("raw.invoices", "report")
    breaking = FakeBreakingChangesCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", FakeAssetCapability())
    calls = [
        tool_call("upstream", "upstream", table="report"),
        tool_call("alert", "breaking_changes"),
    ]

    update = query_nodes.tools_node(
        {"question": "report bị lỗi", "database_id": 1, "messages": [AIMessage(content="", tool_calls=calls)]}
    )

    assert [step["tool"] for step in update["steps"]] == ["traverse", "breaking_changes"]
    assert update["steps"][-1]["error"] == "not_executed"
    assert [message.tool_call_id for message in update["messages"]] == ["upstream", "alert"]
    assert breaking.calls == []


@pytest.mark.parametrize("question", ["impact", "alert rename này báo lỗi gì?"])
def test_breaking_changes_runs_when_batch_has_no_upstream(monkeypatch, question):
    breaking = FakeBreakingChangesCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)

    update = query_nodes.tools_node(
        {
            "question": question,
            "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("alert", "breaking_changes")])],
        }
    )

    assert [step["tool"] for step in update["steps"]] == ["breaking_changes"]
    assert breaking.calls == [(None, 1)]


def test_lineage_only_call_does_not_mark_breaking_changes_checked(monkeypatch):
    add_edge("raw.invoices", "department_revenue")
    breaking = FakeBreakingChangesCapability()
    assets = FakeAssetCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", assets)

    update = query_nodes.tools_node(
        {
            "question": "dữ liệu này từ đâu?",
            "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "upstream", table="department_revenue")])],
        }
    )

    assert [step["tool"] for step in update["steps"]] == ["traverse"]
    assert breaking.calls == []
    assert query_nodes._facts({"database_id": 1, **update})["breaking_changes_checked"] is False


def test_compose_does_not_conclude_lifecycle_clean_without_breaking_changes(monkeypatch):
    add_edge("raw.invoices", "report")
    breaking = FakeBreakingChangesCapability()
    assets = FakeAssetCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", assets)
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    update = query_nodes.tools_node(
        {
            "question": "số liệu tháng này trông kỳ",
            "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "upstream", table="report")])],
        }
    )
    query_nodes.compose_node({"question": "số liệu tháng này trông kỳ", "database_id": 1, **update})

    assert query_nodes._facts({"database_id": 1, **update})["breaking_changes_checked"] is False
    assert breaking.calls == []
    assert assets.calls == []
    assert "When breaking_changes_checked is false" in compose_llm.messages[0].content
    assert "never conclude that no rename, drop, or lifecycle abnormality exists" in compose_llm.messages[0].content


def test_compose_requires_alert_scope_before_calling_an_incomplete_check_clean(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node(
        {
            "question": "report bị lỗi",
            "database_id": 1,
            "confirmed": [
                LineageEdge(source_table="raw.invoices", target_table="report", confidence=1.0, source_type="parser")
            ],
            "pending": [],
            "steps": [{"tool": "breaking_changes", "args": {"tables": ["report"]}}],
        }
    )

    prompt = compose_llm.messages[0].content
    facts = compose_llm.messages[1].content
    assert "state breaking_changes_checked_tables as the alert-check scope" in prompt
    assert "Never call a table clean unless that scope includes the root table and every table" in prompt
    assert '"breaking_changes_checked_tables": ["report"]' in facts


def test_compose_prompt_requires_grounded_diagnostic_hypotheses(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "report bị lỗi", "database_id": 1, "confirmed": [], "pending": []})

    prompt = compose_llm.messages[0].content
    assert "at most three possible causes" in prompt
    assert "anchor each cause to exactly one available fact" in prompt
    assert "must name that exact upstream table.column" in prompt
    assert "hypotheses requiring verification" in prompt
    assert "ask exactly one next question" in prompt


def test_compose_prompt_places_diagnostics_after_breaking_change_rules(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "report bị lỗi", "database_id": 1, "confirmed": [], "pending": []})

    prompt = compose_llm.messages[0].content
    assert prompt.index("When breaking_changes is nonempty") < prompt.index("at most three possible causes")


def test_compose_prompt_includes_breaking_change_repair_guidance(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="answer")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"database_id": 1, "question": "sửa thế nào?", "messages": [], "steps": []})

    prompt = compose_llm.messages[0].content
    assert prompt.index("When breaking_changes is nonempty") < prompt.index("When the user asks how to fix a breaking change")


def test_breaking_changes_prompt_requires_upstream_traverse_after_empty_result():
    prompt = query_nodes.REGISTRY["breaking_changes"].prompt_rules()
    assert "when it returns nothing, call traverse upstream" in prompt


def test_empty_breaking_change_check_and_upstream_edge_reach_compose_facts(monkeypatch):
    edge = LineageEdge(
        source_table="insurance_claims_summary",
        source_column="claim_status",
        target_table="insurance_risk_alerts",
        target_column="high_risk_claim",
        confidence=1.0,
        source_type="parser",
        transform_type="conditional",
        evidence=LineageEvidence(transform_expression="CASE WHEN claim_status = 'denied' THEN TRUE ELSE FALSE END"),
    )
    graph_service.add_edge(1, edge)
    breaking = FakeBreakingChangesCapability()
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", breaking)
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    update = query_nodes.tools_node(
        {
            "question": "high_risk_claim bị sai, tại sao?",
            "database_id": 1,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call("alerts", "breaking_changes", tables=["insurance_risk_alerts"]),
                        tool_call("lineage", "upstream", table="insurance_risk_alerts", column="high_risk_claim"),
                    ],
                )
            ],
        }
    )
    query_nodes.compose_node({"question": "high_risk_claim bị sai, tại sao?", "database_id": 1, **update})

    facts = compose_llm.messages[1].content
    assert '"breaking_changes_checked": true' in facts
    assert "CASE WHEN claim_status" in facts


def test_two_table_question_can_call_a_lineage_tool(monkeypatch, chat_settings):
    chat_settings(description_enabled=False)
    add_edge("raw.orders", "stg.orders")
    agent_llm = CapturingLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)

    result = agent_graph.build_chat_graph().invoke(
        {
            "question": "raw.orders và stg.orders liên quan thế nào?",
            "database_id": 1,
            "messages": [HumanMessage(content="raw.orders và stg.orders liên quan thế nào?")],
        }
    )

    assert result["steps"][0]["tool"] == "traverse"
    assert "If the question asks how two tables relate" not in agent_llm.messages[0].content


def test_compose_prompt_prioritizes_breaking_change_before_dependencies(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "report bị lỗi", "database_id": 1, "confirmed": [], "pending": []})

    assert "replacement before listing dependencies" in compose_llm.messages[0].content


@pytest.mark.parametrize(
    ("state", "graph_is_empty", "expected"),
    [
        (
            {"clarification": {"candidates": ["ecom.orders", "stg.orders"]}},
            False,
            "Vui lòng chọn một bảng: ecom.orders, stg.orders",
        ),
        (
            {"resolved": {"suggestions": ["ecom.orders"]}},
            False,
            "Không tìm thấy bảng. Gợi ý: ecom.orders",
        ),
        ({}, True, "Chưa có dữ liệu lineage. Hãy chạy POST /ingest trước."),
    ],
)
def test_template_answer_uses_data_facts(state, graph_is_empty, expected):
    assert query_nodes._template_answer(state, graph_is_empty=graph_is_empty) == expected


def test_template_answer_keeps_assessment_risk_when_the_llm_answer_is_rejected():
    state = {
        "confirmed": [LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser")],
        "risk": {"edge": "Rủi ro cao: phép join có thể lỗi."},
    }

    answer = query_nodes._template_answer(state)

    assert "stg.orders" in answer
    assert "Rủi ro cao: phép join có thể lỗi." in answer


def test_agent_step_budget_routes_to_compose(chat_settings, monkeypatch):
    chat_settings(CHAT_MAX_AGENT_STEPS=1)
    monkeypatch.setattr(
        query_nodes,
        "get_llm",
        lambda **_: FakeLLM([AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")])]),
    )
    update = query_nodes.agent_node({"question": "impact", "database_id": 1, "messages": [HumanMessage(content="impact")]})
    state = {"question": "impact", "database_id": 1, **update}
    assert query_nodes.route_after_agent(state) == "compose"
    assert update["warnings"] == ["budget_exhausted"]


def test_history_cannot_bypass_table_resolver():
    add_edge("raw.orders", "stg.orders")
    update = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "history": "[lượt trước] bảng đã chốt: legacy.ghost_table",
            "messages": [
                AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="legacy.ghost_table")])
            ],
        }
    )
    assert json.loads(update["messages"][0].content)["error"] == "table_not_found"


def test_facts_expose_conversation_history_for_meta_questions():
    """compose_node trước đây không thấy history (chỉ agent_node thấy) — câu hỏi
    thuần về hội thoại (vd "tôi vừa hỏi gì?") không có gì để trả lời dựa vào."""
    facts = query_nodes._facts(
        {
            "database_id": 1,
            "confirmed": [],
            "pending": [],
            "resolved": {},
            "history": '[lượt trước] Hỏi: "impact orders" | bảng đã chốt: raw.orders | Đã trả lời: "..."',
        }
    )
    assert "impact orders" in facts["conversation_history"]


def test_facts_are_grouped_and_do_not_expose_raw_sql_or_fingerprint():
    edge = LineageEdge(
        source_table="raw.orders",
        target_table="stg.orders",
        confidence=1.0,
        source_type="parser",
        evidence=LineageEvidence(
            file_path="models/stg_orders.sql",
            line_range=[12, 18],
            raw_sql="select secret from raw.orders",
            transform_expression="SUM(amount) AS revenue",
            reasoning="Cột amount được tổng hợp để tạo revenue.",
        ),
    )
    pending_edge = LineageEdge(
        source_table="raw.invoices",
        target_table="stg.invoices",
        confidence=0.6,
        source_type="llm",
        evidence=LineageEvidence(citation_verified=False),
    )
    facts = query_nodes._facts(
        {
            "database_id": 1,
            "confirmed": [edge],
            "pending": [pending_edge],
            "hops": {edge_fingerprint(edge): 1},
            "resolved": {"resolved_table": "raw.orders", "direction": "downstream"},
        }
    )
    rendered = json.dumps(facts)
    assert facts["confirmed"][0]["evidence_file"] == "models/stg_orders.sql"
    assert facts["confirmed"][0]["columns"] == [
        {
            "source_column": None,
            "target_column": None,
            "transform_expression": "SUM(amount) AS revenue",
            "line_range": [12, 18],
        }
    ]
    assert facts["confirmed"][0]["reasoning"] == "Cột amount được tổng hợp để tạo revenue."
    assert facts["inferred_pending"][0]["citation_verified"] is False
    assert "raw_sql" not in rendered
    assert facts["confirmed"][0]["definition_sql"] == "select secret from raw.orders"
    assert edge_fingerprint(edge) not in rendered


def test_ddl_preview_summary_and_facts_use_the_sanitized_payload():
    from src.agents.tools.ddl_preview_tools import PREVIEW_DDL_IMPACT_CAPABILITY, PreviewDdlImpactParams

    add_edge("raw.orders", "stg.orders")
    result = PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="DROP TABLE raw.orders; ALTER TABLE stg.orders DROP COLUMN id;"), 1)
    summary = json.loads(query_nodes._summary(result))
    facts = query_nodes._facts({"database_id": 1, "resolved": result.extra, "confirmed": [], "pending": []})

    assert summary["unsupported"] == 1
    assert summary["unknown_tables"] == []
    assert "table" not in summary
    assert "DROP TABLE" not in json.dumps(facts)


def test_search_sql_content_summary_and_facts_surface_document_content(monkeypatch, database_id):
    """Regression: CapabilityResult.extra["documents"] không khớp bất kỳ nhánh
    dispatch nào trong _summary()/_facts() trước đây (không có "tables", "assets",
    "total_pending", "ddl_preview" hay "resolved_table") — rơi vào nhánh fallback
    impact-style, khiến agent (và LLM soạn câu trả lời cuối) không bao giờ thấy
    nội dung SQL đã tìm được, dù tool chạy đúng và trả kết quả thật."""
    from src.agents.tools.sql_document_tools import SEARCH_SQL_CONTENT_CAPABILITY

    monkeypatch.setattr(
        SEARCH_SQL_CONTENT_CAPABILITY,
        "run",
        lambda params, db_id: CapabilityResult(
            extra={
                "documents": [
                    {"file_path": "models/staging/stg_orders.sql", "statement_order": 0, "table": "stg_orders", "content": "select cents_to_dollars(subtotal) as subtotal"}
                ],
                "truncated": False,
                "total": 1,
            }
        ),
    )
    result = SEARCH_SQL_CONTENT_CAPABILITY.run(None, database_id)

    summary = json.loads(query_nodes._summary(result))
    assert summary["ok"] is True
    assert summary["documents"] == [{"file": "models/staging/stg_orders.sql", "table": "stg_orders"}]
    assert "content" not in json.dumps(summary)  # tool-loop summary không cần nội dung đầy đủ

    facts = query_nodes._facts({"database_id": database_id, "resolved": result.extra, "confirmed": [], "pending": []})
    assert facts["sql_documents"] == [
        {"file": "models/staging/stg_orders.sql", "table": "stg_orders", "content": "select cents_to_dollars(subtotal) as subtotal"}
    ]


def test_ddl_preview_compose_prompt_contracts(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "Cau hoi", "database_id": 1, "confirmed": [], "pending": []})

    prompt = compose_llm.messages[0].content
    assert "do NOT call the script safe to deploy" in prompt
    assert "Never claim the deployment itself will succeed or fail" in prompt
    assert "ddl_preview.risk_by_statement" in prompt


def test_confirmed_evidence_path_is_masked_before_guard_scans():
    edge = LineageEdge(
        source_table="raw.orders",
        target_table="stg.orders",
        confidence=1.0,
        source_type="parser",
        evidence=LineageEvidence(file_path="models/stg_orders.sql"),
    )
    facts = query_nodes._facts({"database_id": 1, "confirmed": [edge], "pending": [], "resolved": {"resolved_table": "raw.orders"}})
    assert query_nodes.unknown_mentions("Evidence: models/stg_orders.sql", facts, {"raw.orders", "stg.orders"}) == []


def test_compose_weaves_stored_table_description_into_prompt(monkeypatch, chat_settings):
    chat_settings(description_enabled=True)
    add_edge("raw.orders", "stg.orders")
    monkeypatch.setattr(
        query_nodes.storage_service,
        "load_descriptions_by_names",
        lambda _database_id, names: {"stg.orders": type("R", (), {"description": "Standardized orders for revenue reporting."})()}
        if "stg.orders" in names
        else {},
    )
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    update = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")])],
        }
    )
    query_nodes.compose_node({"question": "impact", "database_id": 1, **update})

    prompt = compose_llm.messages[1].content
    assert "Standardized orders for revenue reporting." in prompt


def test_compose_skips_description_lookup_when_disabled(monkeypatch, chat_settings):
    chat_settings(description_enabled=False)
    add_edge("raw.orders", "stg.orders")
    called = []
    monkeypatch.setattr(
        query_nodes.storage_service,
        "load_descriptions_by_names",
        lambda _database_id, names: called.append(names) or {},
    )
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    update = query_nodes.tools_node(
        {
            "question": "impact", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")])],
        }
    )
    query_nodes.compose_node({"question": "impact", "database_id": 1, **update})

    assert called == []


def test_prompts_preserve_agent_and_compose_contracts(monkeypatch):
    agent_llm = CapturingLLM([AIMessage(content="DONE")])
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)
    query_nodes.agent_node({"question": "Cau hoi", "database_id": 1, "messages": [HumanMessage(content="Cau hoi")]})
    query_nodes.compose_node({"question": "Cau hoi", "database_id": 1, "confirmed": [], "pending": []})
    agent_prompt = agent_llm.messages[0].content
    compose_prompt = compose_llm.messages[0].content
    assert "single word DONE" in agent_prompt
    assert "do NOT write the final answer" in agent_prompt
    assert "briefly state in Vietnamese why that tool is needed" not in agent_prompt
    assert "Answer the user's question, not the JSON" in compose_prompt
    assert "When candidates is nonempty" in compose_prompt
    assert "When graph_is_empty is true" in compose_prompt
    assert "Always answer in Vietnamese" in compose_prompt
    assert "conversation_history is nonempty" in compose_prompt


def test_agent_prompt_includes_description_search_preference(monkeypatch):
    agent_llm = CapturingLLM([AIMessage(content="DONE")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: agent_llm)

    query_nodes.agent_node({"question": "Cau hoi", "database_id": 1, "messages": [HumanMessage(content="Cau hoi")]})

    assert "search_by_description (not search_tables)" in agent_llm.messages[0].content


def test_agent_prompt_preserves_search_tables_rule(monkeypatch):
    agent_llm = CapturingLLM([AIMessage(content="DONE")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: agent_llm)

    query_nodes.agent_node({"question": "Cau hoi", "database_id": 1, "messages": [HumanMessage(content="Cau hoi")]})

    assert "Use search_tables only when you need to discover a real table name" in agent_llm.messages[0].content


def test_build_clarification_removes_table_and_keeps_column():
    clarification = query_nodes.build_clarification(
        tool_call("one", "downstream", table="orders", column="amount"),
        CapabilityResult(error="ambiguous", extra={"mention": "orders", "candidates": ["ecom.orders"]}),
        "impact",
    )
    assert clarification["resume_args"] == {"column": "amount", "direction": "downstream"}


def test_build_clarification_removes_missing_column_and_keeps_table():
    clarification = query_nodes.build_clarification(
        tool_call("one", "downstream", table="orders", column="amount"),
        CapabilityResult(error="column_not_found", extra={"mention": "amount", "candidates": ["amount_paid"]}),
        "impact",
    )
    assert clarification["slot"] == "column"
    assert clarification["resume_args"] == {"table": "orders", "direction": "downstream"}


def test_verify_warns_without_replacing_table_outside_turn_vocabulary(monkeypatch):
    monkeypatch.setattr(query_nodes.get_settings(), "chat_verify_mode", "warn")
    update = query_nodes.verify_node(
        {
            "database_id": 1,
            "answer": "raw.customers is involved",
            "vocabulary": {"ecom.orders"},
            "confirmed": [],
            "pending": [],
        }
    )
    assert "answer" not in update
    assert update["warnings"][0].startswith("answer_unverified_unknown_tables")
    assert not update["warnings"][0].startswith("answer_rejected_")


def test_verify_replace_rejects_table_outside_turn_vocabulary(monkeypatch):
    monkeypatch.setattr(query_nodes.get_settings(), "chat_verify_mode", "replace")
    update = query_nodes.verify_node(
        {
            "database_id": 1,
            "answer": "raw.customers is involved",
            "vocabulary": {"ecom.orders"},
            "confirmed": [],
            "pending": [],
        }
    )

    assert update["answer"] == "Lineage đã ghi nhận: chưa có cạnh nào"
    assert update["warnings"][0].startswith("answer_rejected_unknown_tables")


def test_get_asset_batches_accumulate_in_state_and_facts(monkeypatch):
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", FakeAssetCapability())
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("one", "get_asset", tables=["raw.orders"])]),
            AIMessage(content="", tool_calls=[tool_call("two", "get_asset", tables=["mart.orders"])]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)

    result = agent_graph.build_chat_graph().invoke({"question": "why?", "database_id": 1, "messages": [HumanMessage(content="why?")]})

    assert set(result["assets"]) == {"raw.orders", "mart.orders"}
    assert set(query_nodes._facts(result)["assets"]) == {"raw.orders", "mart.orders"}


def test_get_asset_summary_has_routing_metadata_but_not_description_text(monkeypatch):
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", FakeAssetCapability())
    update = query_nodes.tools_node(
        {
            "question": "why?", "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "get_asset", tables=["mart.orders"])])],
        }
    )
    summary = json.loads(update["messages"][0].content)
    asset_summary = summary["assets"][0]
    assert asset_summary["defined_in"] == "models/mart.orders.sql"
    assert asset_summary["columns_produced"] == ["order_id"]
    assert asset_summary["has_description"] is False
    assert "upstream_tables" not in asset_summary
    assert "previous_names" not in asset_summary
    assert "description" not in asset_summary

    facts = query_nodes._facts({"database_id": 1, "assets": update["assets"], "confirmed": [], "pending": []})
    answer = "models/mart.orders.sql order_id old_orders mart.orders"
    assert query_nodes.unknown_mentions(answer, facts, update["vocabulary"]) == []


def test_analyze_query_keeps_resolved_columns_through_a_following_traverse(monkeypatch):
    add_edge("raw.invoices", "stg.invoices")
    agent_llm = FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    tool_call(
                        "query", "analyze_query", sql="SELECT amount_paid AS total_revenue FROM stg.invoices"
                    )
                ],
            ),
            AIMessage(content="", tool_calls=[tool_call("upstream", "traverse", table="stg.invoices")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="stg.invoices has raw.invoices as an upstream source.")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)

    result = agent_graph.build_chat_graph().invoke(
        {
            "question": "Where does this query get data: SELECT amount_paid AS total_revenue FROM stg.invoices",
            "database_id": 1,
            "messages": [HumanMessage(content="Where does this query get data")],
        }
    )

    assert [step["tool"] for step in result["steps"]] == ["analyze_query", "traverse"]
    assert result["query_columns"] == [
        {
            "source_table": "stg.invoices",
            "source_column": "amount_paid",
            "output_column": "total_revenue",
            "resolved": True,
        }
    ]
    assert query_nodes._facts(result)["query_columns"] == result["query_columns"]


def test_facts_expose_only_safe_lookup_trace():
    facts = query_nodes._facts(
        {
            "database_id": 1,
            "confirmed": [],
            "pending": [],
            "steps": [
                {
                    "tool": "get_asset",
                    "args": {"tables": ["stg.orders"]},
                    "summary": "private result",
                    "duration_ms": 12,
                    "error": None,
                }
            ],
        }
    )

    assert facts["lookups"] == [{"tool": "get_asset", "args": {"tables": ["stg.orders"]}}]
    assert "private result" not in json.dumps(facts["lookups"])


def test_compose_prompt_puts_missing_fact_rule_before_disclosure_rules(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "Cau hoi", "database_id": 1, "confirmed": [], "pending": []})

    prompt = compose_llm.messages[0].content
    assert prompt.index("If the collected facts do not answer") < prompt.index("Cite evidence_file")
    assert "A table description or lineage relationship is NOT a filter condition" in prompt


def test_facts_group_edges_and_keep_lowest_confidence():
    edges = [
        LineageEdge(
            source_table="raw.orders",
            source_column=source,
            target_table="stg.orders",
            target_column=target,
            transform_type="direct",
            confidence=confidence,
            source_type="parser",
            evidence=LineageEvidence(transform_expression=source, line_range=[line, line]),
        )
        for source, target, confidence, line in [
            ("id", "order_id", 1.0, 1),
            ("status", "status", 0.8, 2),
            ("amount", "amount", 1.0, 3),
            ("created_at", "created_at", 1.0, 4),
            ("updated_at", "updated_at", 1.0, 5),
        ]
    ]

    facts = query_nodes._facts({"database_id": 1, "confirmed": edges, "pending": []})

    assert len(facts["confirmed"]) == 1
    assert len(facts["confirmed"][0]["columns"]) == 5
    assert facts["confirmed"][0]["confidence"] == 0.8
    assert facts["confirmed"][0]["confidence_varies"] is True


def test_column_description_summary_and_facts_keep_the_answer_shape():
    result = CapabilityResult(
        extra={
            "columns": [
                {"table": "stg.invoices", "column": "amount_paid", "description": "Paid invoice amount."}
            ],
            "truncated": False,
            "total": 1,
        }
    )

    summary = json.loads(query_nodes._summary(result))
    facts = query_nodes._facts(
        {
            "database_id": 1,
            "confirmed": [],
            "pending": [],
            "matched_columns": result.extra["columns"],
        }
    )

    assert summary == {
        "ok": True,
        "columns": [{"table": "stg.invoices", "column": "amount_paid"}],
        "truncated": False,
        "total": 1,
    }
    assert facts["matched_columns"] == result.extra["columns"]


def test_column_description_match_kind_reaches_summary_and_facts(monkeypatch):
    result = CapabilityResult(
        extra={
            "columns": [{"table": "mart.revenue", "column": "projected_revenue", "description": None}],
            "truncated": False,
            "total": 1,
            "match_kind": "exact",
        }
    )
    summary = json.loads(query_nodes._summary(result))
    monkeypatch.setattr(query_nodes.REGISTRY["search_column_description"], "run", lambda *_args: result)
    update = query_nodes.tools_node(
        {
            "question": "projected_revenue tính thế nào?",
            "database_id": 1,
            "messages": [AIMessage(content="", tool_calls=[tool_call("one", "search_column_description", query="projected_revenue")])],
        }
    )

    assert summary["match_kind"] == "exact"
    assert update["matched_columns"][0]["match_kind"] == "exact"


def test_definition_sql_is_deduplicated_and_respects_per_file_and_total_budgets(chat_settings):
    first_sql = "SELECT * FROM raw.orders WHERE status = 'paid'"
    long_sql = "X" * 2100
    edges = [
        LineageEdge(source_table="raw.orders", target_table="stg.orders", confidence=1.0, source_type="parser", evidence=LineageEvidence(raw_sql=first_sql)),
        LineageEdge(source_table="raw.orders", target_table="stg.orders_two", confidence=1.0, source_type="parser", evidence=LineageEvidence(raw_sql=first_sql)),
        LineageEdge(source_table="stg.orders", target_table="mart.orders", confidence=1.0, source_type="parser", evidence=LineageEvidence(raw_sql=long_sql)),
    ]
    chat_settings(CHAT_MAX_DEFINITION_CHARS=2100)
    facts = query_nodes._facts({"database_id": 1, "confirmed": edges, "pending": [], "hops": {edge_fingerprint(edges[0]): 1, edge_fingerprint(edges[1]): 1, edge_fingerprint(edges[2]): 2}})
    definitions = [group["definition_sql"] for group in facts["confirmed"] if group["definition_sql"]]

    assert definitions == [first_sql, long_sql[:2000]]
    assert facts["confirmed"][-1]["definition_truncated"] is True
    assert facts["definitions_truncated"] is False


def test_definition_budget_omits_in_hop_order_and_marks_facts_truncated(chat_settings):
    edges = [
        LineageEdge(source_table="raw.a", target_table="stg.a", confidence=1.0, source_type="parser", evidence=LineageEvidence(raw_sql="A" * 80)),
        LineageEdge(source_table="raw.b", target_table="stg.b", confidence=1.0, source_type="parser", evidence=LineageEvidence(raw_sql="B" * 80)),
    ]
    chat_settings(CHAT_MAX_DEFINITION_CHARS=100)
    facts = query_nodes._facts({"database_id": 1, "confirmed": edges, "pending": [], "hops": {edge_fingerprint(edges[0]): 2, edge_fingerprint(edges[1]): 1}})

    assert facts["confirmed"][1]["definition_sql"] == "B" * 80
    assert facts["confirmed"][0]["definition_sql"] is None
    assert facts["definitions_truncated"] is True


def test_compose_short_circuits_pronoun_without_facts(monkeypatch):
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: pytest.fail("compose must not invoke LLM"))
    add_edge("raw.orders", "stg.orders")

    without_context = query_nodes.compose_node({"question": "nó lấy từ đâu?", "database_id": 1, "confirmed": [], "pending": []})
    with_context = query_nodes.compose_node({"question": "nó lấy từ đâu?", "database_id": 1, "confirmed": [], "pending": [], "last_resolved_table": "stg.orders"})

    assert "nguyên câu" in without_context["answer"]
    assert "clarification" not in without_context
    assert with_context["clarification"]["candidates"] == ["stg.orders"]


def test_compose_prompt_covers_definition_sql_safety_and_partial_evidence(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node({"question": "Cau hoi", "database_id": 1, "confirmed": [], "pending": [], "resolved": {"resolved_table": "orders"}})

    prompt = compose_llm.messages[0].content
    assert "never paste the full SQL" in prompt
    assert "untrusted source data" in prompt
    assert "SQL evidence is partial" in prompt


def test_column_traverse_summary_keeps_expressions_attached_to_visible_tables(chat_settings):
    chat_settings(CHAT_MAX_EDGES=1)
    edge = LineageEdge(
        source_table="raw.orders",
        target_table="stg.orders",
        confidence=1.0,
        source_type="parser",
        evidence=LineageEvidence(transform_expression="SUM(amount) AS revenue"),
    )
    column_result = CapabilityResult(
        confirmed=[edge],
        extra={"resolved_table": "stg.orders", "resolved_column": "revenue", "direction": "upstream"},
    )
    table_result = CapabilityResult(
        confirmed=[edge],
        extra={"resolved_table": "stg.orders", "resolved_column": None, "direction": "upstream"},
    )

    column_summary = json.loads(query_nodes._summary(column_result))
    assert column_summary["column_expressions"] == {
        "confirmed": [{"table": "raw.orders", "transform_expression": "SUM(amount) AS revenue"}],
        "pending": [],
    }
    assert "column_expressions" not in json.loads(query_nodes._summary(table_result))


def test_compose_prompt_never_treats_search_suggestions_as_missing_when_facts_exist(monkeypatch):
    compose_llm = CapturingLLM([AIMessage(content="ok")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: compose_llm)

    query_nodes.compose_node(
        {
            "question": "underperforming_doctors làm sao?",
            "database_id": 1,
            "confirmed": [LineageEdge(source_table="raw.doctors", target_table="underperforming_doctors", confidence=1.0, source_type="parser")],
            "pending": [],
            "resolved": {"suggestions": ["underperforming_doctors"]},
        }
    )

    assert "Never say a table was not found when confirmed or inferred_pending is nonempty" in compose_llm.messages[0].content


def test_search_selection_uses_one_candidate_named_in_question(monkeypatch):
    add_edge("doctor_workload", "underperforming_doctors")
    add_edge("raw_doctors", "stg_doctors")
    agent_llm = FakeLLM(
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="doctor")]),
            AIMessage(content="", tool_calls=[tool_call("traverse", "upstream", table="underperforming_doctors")]),
            AIMessage(content="DONE"),
        ]
    )
    compose_llm = FakeLLM([AIMessage(content="rule")])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent_llm if kwargs.get("tools") else compose_llm)
    question = "làm thế nào để doctor được đánh dấu là underperforming_doctors?"

    result = agent_graph.build_chat_graph().invoke(
        {"question": question, "database_id": 1, "messages": [HumanMessage(content=question)]}
    )

    first_tool_payload = json.loads(result["messages"][2].content)
    assert first_tool_payload["tables"] == ["underperforming_doctors"]
    assert result.get("clarification") is None
    assert len(result["steps"]) == 2
    assert result["steps"][0]["error"] is None


@pytest.mark.parametrize(
    "question",
    [
        "doctor_workload và underperforming_doctors liên quan thế nào?",
        "làm thế nào để doctor được đánh dấu?",
        "doctor_workloads là gì?",
    ],
)
def test_search_selection_keeps_clarification_without_one_complete_candidate(monkeypatch, question):
    add_edge("doctor_workload", "underperforming_doctors")
    add_edge("raw_doctors", "stg_doctors")
    agent_llm = FakeLLM([AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="doctor")])])
    monkeypatch.setattr(query_nodes, "get_llm", lambda **_kwargs: agent_llm)

    result = agent_graph.build_chat_graph().invoke(
        {"question": question, "database_id": 1, "messages": [HumanMessage(content=question)]}
    )

    assert result["steps"][0]["error"] == "needs_selection"
    assert result["clarification"]["candidates"] == ["doctor_workload", "raw_doctors", "stg_doctors", "underperforming_doctors"]
