import json
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.agents.chat import session as chat_session
from src.agents.chat.base import CapabilityResult
from src.agents.nodes import query_nodes
from src.agents.tools.asset_tools import GetAssetParams
from src.agents.tools.breaking_change_tools import BreakingChangesParams
from src.config import get_settings
from src.models.schemas import AssetProfile, LineageEdge
from src.services import chat_service, graph_service, review_service, storage_service

# client fixture (conftest.py::seed_user) luôn dùng X-User-Id: 1
SEED_USER_ID = 1


@pytest.fixture(autouse=True)
def fresh_chat_state(database_id):
    graph_service._reset_graph(database_id, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(database_id, None)
    review_service._reset()


@pytest.fixture(autouse=True)
def fake_chat_storage(monkeypatch):
    """Giả lập chat_sessions/chat_turns bằng dict/list RAM — xem cùng fixture
    trong tests/test_agents/test_chat_session.py."""
    sessions: dict[tuple[int, int], dict | None] = {}
    turns: list[dict] = []

    def fake_ensure(database_id, user_id, tx=None):
        sessions.setdefault((database_id, user_id), None)

    def fake_get(database_id, user_id, tx=None):
        if (database_id, user_id) not in sessions:
            return None
        return storage_service.ChatSessionRow(
            database_id=database_id,
            user_id=user_id,
            pending_clarification=sessions[(database_id, user_id)],
            updated_at=datetime.now(UTC),
        )

    def fake_set_clarification(database_id, user_id, pending_clarification, tx=None):
        sessions[(database_id, user_id)] = pending_clarification

    def fake_insert_turn(database_id, user_id, question, resolved_table, answer, tx=None):
        turns.append(
            {"database_id": database_id, "user_id": user_id, "question": question, "resolved_table": resolved_table, "answer": answer}
        )

    def fake_list_recent(database_id, user_id, limit, tx=None):
        matching = [t for t in turns if t["database_id"] == database_id and t["user_id"] == user_id]
        recent = matching[-limit:]
        return [
            storage_service.ChatTurnRow(
                id=i, database_id=t["database_id"], user_id=t["user_id"], question=t["question"],
                resolved_table=t["resolved_table"], answer=t["answer"], created_at=datetime.now(UTC),
            )
            for i, t in enumerate(recent)
        ]

    def fake_clear(database_id, user_id, tx=None):
        turns[:] = [t for t in turns if not (t["database_id"] == database_id and t["user_id"] == user_id)]
        sessions[(database_id, user_id)] = None

    monkeypatch.setattr(chat_session.storage_service, "ensure_chat_session", fake_ensure)
    monkeypatch.setattr(chat_session.storage_service, "get_chat_session", fake_get)
    monkeypatch.setattr(chat_session.storage_service, "set_chat_session_clarification", fake_set_clarification)
    monkeypatch.setattr(chat_session.storage_service, "insert_chat_turn", fake_insert_turn)
    monkeypatch.setattr(chat_session.storage_service, "list_recent_chat_turns", fake_list_recent)
    monkeypatch.setattr(chat_session.storage_service, "clear_chat_session", fake_clear)
    yield {"sessions": sessions, "turns": turns}


@pytest.fixture
def chat_settings(monkeypatch):
    def apply(**overrides):
        for key, value in overrides.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()

    get_settings.cache_clear()
    yield apply
    get_settings.cache_clear()


def set_streaming_compose(monkeypatch, agent_responses, answer="nguon du lieu da xac nhan"):
    """Nhu set_llms nhung compose la model gia BIET STREAM that (GenericFakeChatModel),
    nen LangGraph stream_mode="messages" moi nha ra token. FakeLLM thuong khong phai
    model LangChain nen khong sinh callback nao -> moi phep kiem ve token se vo nghia."""
    agent = FakeLLM(agent_responses)
    compose = GenericFakeChatModel(messages=iter([AIMessage(content=answer)] * 4))
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent if kwargs.get("tools") else compose)
    return agent, compose


def add_edge(database_id, source, target, *, source_type="parser", confidence=1.0):
    edge = LineageEdge(source_table=source, target_table=target, confidence=confidence, source_type=source_type)
    if source_type == "llm":
        review_service.add_pending(database_id, [edge])
    else:
        graph_service.add_edge(database_id, edge)


def tool_call(call_id, name, **args):
    if name in {"upstream", "downstream"}:
        args["direction"] = name
        name = "traverse"
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.seen = []

    def invoke(self, messages):
        self.calls += 1
        self.seen.append(messages)
        return next(self.responses)

    def stream(self, messages):
        yield self.invoke(messages)


class FakeBreakingChangesCapability:
    name = "breaking_changes"
    description = "test"
    Params = BreakingChangesParams

    def run(self, _params, _database_id):
        return CapabilityResult(extra={"breaking_changes": []})

    def vocabulary(self, _result):
        return set()

    def prompt_rules(self):
        return "test"


class FakeAssetCapability:
    name = "get_asset"
    description = "test"
    Params = GetAssetParams

    def run(self, params, _database_id):
        return CapabilityResult(
            extra={
                "assets": [
                    AssetProfile(
                        name=table,
                        is_defined=False,
                        upstream_count=0,
                        downstream_count=0,
                        modified_count=0,
                        is_dropped=False,
                        pending_count=0,
                    )
                    for table in params.tables
                ],
                "skipped": [],
                "truncated": False,
            }
        )

    def vocabulary(self, result):
        return {asset.name for asset in result.extra["assets"]}

    def prompt_rules(self):
        return "test"


def set_llms(monkeypatch, agent_responses, answer="answer"):
    agent = FakeLLM(agent_responses)
    compose = FakeLLM([AIMessage(content=answer)] * 4)
    monkeypatch.setattr(query_nodes, "get_llm", lambda **kwargs: agent if kwargs.get("tools") else compose)
    return agent, compose


@pytest.mark.asyncio
async def test_chat_empty_graph_returns_no_edges(client, monkeypatch, database_id):
    set_llms(
        monkeypatch,
        [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orders")]), AIMessage(content="DONE")],
    )
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "lineage?"})
    assert response.status_code == 200
    assert response.json()["confirmed"] == []
    assert response.json()["answer"]


@pytest.mark.asyncio
async def test_chat_maps_confirmed_pending_and_steps(client, monkeypatch, database_id):
    add_edge(database_id, "raw.orders", "stg.orders")
    add_edge(database_id, "stg.orders", "legacy_ltv", source_type="llm", confidence=0.5)
    set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="DONE"),
        ],
        answer="raw.orders affects stg.orders",
    )
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "Bảng nào liên quan tới raw.orders?"})
    body = response.json()
    assert body["steps"][0]["resolved"]["direction"] == "downstream"
    assert [edge["hitl_status"] for edge in body["confirmed"]] == ["confirmed"]
    assert [edge["hitl_status"] for edge in body["inferred_pending"]] == ["pending"]
    assert body["steps"] == [
        {
            "tool": "traverse",
            "args": {"table": "raw.orders", "direction": "downstream"},
            "resolved": {"table": "raw.orders", "column": None, "direction": "downstream"},
            "error": None,
            "summary": "1 confirmed, 1 pending",
            "duration_ms": body["steps"][0]["duration_ms"],
            "agent_step": 1,
        }
    ]
    assert body["stop_reason"] == "completed"
    assert body["tool_calls_used"] == 1


@pytest.mark.asyncio
async def test_diagnostic_chat_does_not_inject_a_triage_trace_via_api(client, monkeypatch, database_id):
    add_edge(database_id, "raw.invoices", "stg.invoices")
    add_edge(database_id, "stg.invoices", "department_revenue")
    monkeypatch.setitem(query_nodes.REGISTRY, "breaking_changes", FakeBreakingChangesCapability())
    monkeypatch.setitem(query_nodes.REGISTRY, "get_asset", FakeAssetCapability())
    set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "upstream", table="department_revenue")]),
            AIMessage(content="DONE"),
        ],
    )

    response = await client.post(
        "/api/v1/chat",
        json={"database_id": database_id, "question": "department_revenue bị lỗi, tại sao?"},
    )

    steps = response.json()["steps"]
    assert [step["tool"] for step in steps] == ["traverse"]


@pytest.mark.asyncio
async def test_chat_clarification_resumes_without_agent_llm(client, monkeypatch, database_id):
    add_edge(database_id, "ecom.orders", "stg.orders")
    add_edge(database_id, "stg.orders", "fct_sales")
    agent, _ = set_llms(
        monkeypatch,
        [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orders")])],
        answer="stg.orders affects fct_sales",
    )
    first = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "impact orders"})
    assert first.json()["clarification_options"] == ["ecom.orders", "stg.orders"]
    assert first.json()["session_id"] == str(SEED_USER_ID)
    # session_id gửi lên chỉ mang tính tương thích ngược — định danh thật là
    # X-User-Id (client fixture luôn gửi cùng 1 user), không cần gửi lại giá
    # trị này để lượt 2 vẫn nhớ đúng clarification của lượt 1.
    second = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "2"})
    assert second.json()["steps"][0]["resolved"]["table"] == "stg.orders"
    assert second.json()["steps"][0]["agent_step"] == 0
    assert second.json()["steps"][0]["duration_ms"] >= 0
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_chat_writes_a_trace_line(client, monkeypatch, tmp_path, database_id):
    monkeypatch.setattr(chat_service, "CHAT_TRACE_DIR", tmp_path)
    set_llms(monkeypatch, [AIMessage(content="DONE")])

    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "lineage?"})

    files = list(tmp_path.glob("*.jsonl"))
    assert response.status_code == 200
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    trace = json.loads(lines[0])
    assert trace["question"] == "lineage?"
    assert trace["steps"] == []
    assert trace["stop_reason"] == "completed"


@pytest.mark.asyncio
async def test_resume_chat_writes_a_trace_line(client, monkeypatch, tmp_path, database_id):
    monkeypatch.setattr(chat_service, "CHAT_TRACE_DIR", tmp_path)
    add_edge(database_id, "ecom.orders", "stg.orders")
    set_llms(
        monkeypatch,
        [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orders")])],
        answer="stg.orders affects fct_sales",
    )

    first = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "impact orders"})
    second = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "2", "session_id": first.json()["session_id"]})

    traces = [json.loads(line) for line in next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    assert second.status_code == 200
    assert len(traces) == 2
    assert traces[-1]["steps"][0]["agent_step"] == 0


@pytest.mark.asyncio
async def test_trace_write_failure_keeps_the_chat_response(client, monkeypatch, database_id):
    monkeypatch.setattr(chat_service, "_append_trace", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    set_llms(monkeypatch, [AIMessage(content="DONE")])

    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "lineage?"})

    assert response.status_code == 200
    assert "chat_trace_write_failed" in response.json()["warnings"]


@pytest.mark.asyncio
async def test_trace_can_be_disabled(client, monkeypatch, tmp_path, database_id, chat_settings):
    chat_settings(CHAT_TRACE_ENABLED=False)
    monkeypatch.setattr(chat_service, "CHAT_TRACE_DIR", tmp_path)
    set_llms(monkeypatch, [AIMessage(content="DONE")])

    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "lineage?"})

    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_chat_test_run_does_not_write_to_the_repository_logs(client, monkeypatch, tmp_path, database_id):
    monkeypatch.chdir(tmp_path)
    set_llms(monkeypatch, [AIMessage(content="DONE")])

    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "lineage?"})

    assert response.status_code == 200
    assert not Path("logs/chat-traces").exists()


@pytest.mark.asyncio
async def test_search_selection_restarts_original_question_with_the_selected_table_pinned(client, monkeypatch, database_id):
    add_edge(database_id, "ecom.orders", "stg.orders")
    agent, _ = set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="orders")]),
            AIMessage(content="", tool_calls=[tool_call("trace", "downstream", table="wrong.table")]),
            AIMessage(content="DONE"),
        ],
        answer="ecom.orders affects stg.orders",
    )

    first = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "impact orders"})
    second = await client.post(
        "/api/v1/chat",
        json={"database_id": database_id, "question": "1", "session_id": first.json()["session_id"]},
    )

    assert first.json()["clarification_options"] == ["ecom.orders", "stg.orders"]
    assert second.json()["steps"][0]["args"]["table"] == "ecom.orders"
    assert second.json()["steps"][0]["resolved"]["table"] == "ecom.orders"
    assert agent.calls == 3


@pytest.mark.asyncio
async def test_search_selection_rewrites_the_original_question_with_the_chosen_table(client, monkeypatch, database_id):
    add_edge(database_id, "raw.final", "revenue_alerts_final")
    add_edge(database_id, "raw.staging", "revenue_alerts_staging")
    agent, _ = set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("search-1", "search_tables", query="revenue_alert")]),
            AIMessage(content="", tool_calls=[tool_call("search-2", "search_tables", query="revenue_alerts_staging")]),
            AIMessage(content="DONE"),
        ],
    )

    first = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "revenue_alert có gì?"})
    second = await client.post(
        "/api/v1/chat", json={"database_id": database_id, "question": "revenue_alerts_staging"}
    )

    assert first.json()["clarification_options"] == ["revenue_alerts_final", "revenue_alerts_staging"]
    assert second.json()["steps"][0]["args"]["query"] == "revenue_alerts_staging"
    assert "revenue_alert" not in second.json()["answer"]
    assert agent.seen[1][-1].content == "revenue_alerts_staging có gì?"


@pytest.mark.asyncio
async def test_a_new_long_question_containing_a_candidate_does_not_resume_the_old_question(client, monkeypatch, database_id):
    add_edge(database_id, "raw.final", "revenue_alerts_final")
    add_edge(database_id, "raw.staging", "revenue_alerts_staging")
    agent, _ = set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("search", "search_tables", query="revenue_alert")]),
            AIMessage(content="", tool_calls=[tool_call("trace", "downstream", table="revenue_alerts_staging")]),
            AIMessage(content="DONE"),
        ],
    )

    await client.post("/api/v1/chat", json={"database_id": database_id, "question": "revenue_alert có gì?"})
    second = await client.post(
        "/api/v1/chat",
        json={"database_id": database_id, "question": "revenue_alerts_staging ảnh hưởng tới những bảng nào vậy nhỉ"},
    )

    assert second.json()["steps"][0]["args"]["table"] == "revenue_alerts_staging"
    assert agent.calls == 3
    assert agent.seen[1][-1].content == "revenue_alerts_staging ảnh hưởng tới những bảng nào vậy nhỉ"


@pytest.mark.asyncio
async def test_chat_reports_table_not_found(client, monkeypatch, database_id):
    add_edge(database_id, "ecom.orders", "stg.orders")
    set_llms(
        monkeypatch,
        [AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orderz")]), AIMessage(content="DONE")],
    )
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "impact"})
    assert response.json()["steps"][0]["args"]["table"] == "orderz"
    assert response.json()["steps"][0]["error"] == "table_not_found"


@pytest.mark.asyncio
async def test_chat_requires_user_selection_from_suggested_table_names(client, monkeypatch, database_id):
    add_edge(database_id, "ecom.orders", "stg.orders")
    set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="orderz")]),
            AIMessage(content="", tool_calls=[tool_call("two", "downstream", table="ecom.orders")]),
            AIMessage(content="DONE"),
        ],
        answer="ecom.orders affects stg.orders",
    )
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "impact"})
    assert response.json()["steps"][0]["error"] == "table_not_found"
    assert response.json()["clarification_options"]
    assert response.json()["suggestions"] == response.json()["clarification_options"]


@pytest.mark.asyncio
async def test_chat_relationship_is_unsupported(client, monkeypatch, database_id):
    add_edge(database_id, "ecom.orders", "stg.orders")
    set_llms(monkeypatch, [AIMessage(content="DONE")])
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": "relationship between orders and customers"})
    body = response.json()
    assert body["steps"] == []


@pytest.mark.asyncio
async def test_chat_rejects_empty_question(client, database_id):
    response = await client.post("/api/v1/chat", json={"database_id": database_id, "question": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_turn_is_recorded_append_only(client, monkeypatch, database_id, fake_chat_storage):
    set_llms(monkeypatch, [AIMessage(content="DONE"), AIMessage(content="DONE")])
    await client.post("/api/v1/chat", json={"database_id": database_id, "question": "q1"})
    await client.post("/api/v1/chat", json={"database_id": database_id, "question": "q2"})
    saved = [t for t in fake_chat_storage["turns"] if t["database_id"] == database_id and t["user_id"] == SEED_USER_ID]
    assert [t["question"] for t in saved] == ["q1", "q2"]


def test_chat_stream_keeps_every_step_across_two_tool_rounds(monkeypatch, database_id, fake_chat_storage):
    add_edge(database_id, "raw.orders", "stg.orders")
    add_edge(database_id, "stg.orders", "mart.orders")
    set_llms(monkeypatch, [
        AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
        AIMessage(content="", tool_calls=[tool_call("two", "downstream", table="stg.orders")]),
        AIMessage(content="DONE"),
    ])
    events = list(chat_service.answer_question_stream("impact raw.orders", SEED_USER_ID, database_id))
    steps = [event["data"] for event in events if event["event"] == "step"]
    done = next(event["data"] for event in events if event["event"] == "done")
    assert [step.tool for step in steps] == ["traverse", "traverse"]
    assert [step.tool for step in done.steps] == ["traverse", "traverse"]
    assert len(done.confirmed) == 2
    assert len(fake_chat_storage["turns"]) == 1


@pytest.mark.asyncio
async def test_chat_reset_clears_history(client, monkeypatch, database_id, fake_chat_storage):
    set_llms(monkeypatch, [AIMessage(content="DONE")])
    await client.post("/api/v1/chat", json={"database_id": database_id, "question": "q1"})

    response = await client.post("/api/v1/chat/reset", params={"database_id": database_id})
    assert response.status_code == 204

    remaining = [t for t in fake_chat_storage["turns"] if t["database_id"] == database_id and t["user_id"] == SEED_USER_ID]
    assert remaining == []


def test_stream_emits_no_token_when_verify_mode_replaces_the_answer(monkeypatch, database_id, chat_settings):
    """chat_verify_mode="replace" cho phep verify_node VUT ca cau tra loi va thay bang
    template. Da stream chu ra thi khong rut lai duoc, nen o che do do khong duoc phat
    token nao — chi step + done. Toan bo bao ve dang nam o mot dieu kien trong
    chat_service; day la cong canh no."""
    chat_settings(chat_verify_mode="replace")
    add_edge(database_id, "raw.orders", "stg.orders")
    set_streaming_compose(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="DONE"),
        ],
    )

    events = list(chat_service.answer_question_stream("impact raw.orders", SEED_USER_ID, database_id))

    kinds = [event["event"] for event in events]
    assert "token" not in kinds
    assert "step" in kinds and kinds[-1] == "done"


def test_stream_never_leaks_a_tool_payload_as_an_answer_token(monkeypatch, database_id):
    """LangGraph stream_mode="messages" nha CA noi dung ToolMessage cua node tools.
    Khong loc theo langgraph_node == "compose" thi JSON tho cua tool chay thang vao
    bong bong chat."""
    add_edge(database_id, "raw.orders", "stg.orders")
    set_streaming_compose(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="DONE"),
        ],
    )

    events = list(chat_service.answer_question_stream("impact raw.orders", SEED_USER_ID, database_id))

    tokens = [event["data"]["text"] for event in events if event["event"] == "token"]
    assert tokens, "phai co token that de phep kiem nay co nghia"
    assert all('"ok"' not in text and "confirmed" not in text for text in tokens)


def test_stream_persists_nothing_when_the_client_disconnects_early(monkeypatch, tmp_path, database_id, fake_chat_storage):
    """R11/R13: ghi trang thai dat NGAY TRUOC done, nen ngat som la luot do coi nhu chua
    tung xay ra — khong turn, khong clarification, khong trace. Row session rong do
    ensure_chat_session() tao thi chap nhan (xem C-6)."""
    monkeypatch.setattr(chat_service, "CHAT_TRACE_DIR", tmp_path)
    add_edge(database_id, "raw.orders", "stg.orders")
    set_llms(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call("one", "downstream", table="raw.orders")]),
            AIMessage(content="DONE"),
        ],
    )

    stream = chat_service.answer_question_stream("impact raw.orders", SEED_USER_ID, database_id)
    first = next(stream)
    stream.close()

    assert first["event"] in {"step", "thought", "token"}
    assert fake_chat_storage["turns"] == []
    assert fake_chat_storage["sessions"][(database_id, SEED_USER_ID)] is None
    assert list(tmp_path.glob("*.jsonl")) == []
