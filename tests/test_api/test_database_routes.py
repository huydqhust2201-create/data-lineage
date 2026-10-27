import psycopg2
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from src.api.deps import ensure_database_role
from src.config import get_settings
from src.main import app
from src.models.schemas import LineageEdge, PendingColumnDescription, PendingDescription
from src.services import (
    auth_service,
    column_description_review_service,
    description_review_service,
    graph_service,
    review_service,
    storage_service,
)


def _bearer_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_service.create_access_token(user_id)}"}


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres không sẵn sàng ở DATABASE_URL")


def _edge(source: str, target: str) -> LineageEdge:
    return LineageEdge(source_table=source, target_table=target, confidence=1.0, source_type="parser")


def _seed_graph(database_id: int, source: str, target: str) -> None:
    graph_service._reset_graph(database_id, None)
    graph_service.add_edge(database_id, _edge(source, target))


def _node_record(name: str) -> storage_service.NodeRecord:
    return storage_service.NodeRecord(
        current_name=name,
        defined_in=None,
        source_file=None,
        columns_produced=[],
        columns_consumed=[],
        upstream_tables=[],
        downstream_tables=[],
        source_types=[],
        transform_types=[],
        confidence_min=None,
        confidence_max=None,
    )


def _column_description(node_id: int, description: str, evidence_hash: str) -> storage_service.ColumnDescriptionRecord:
    return storage_service.ColumnDescriptionRecord(
        node_id=node_id,
        column_name="order_id",
        description=description,
        source="llm",
        label="schema_inferred",
        confidence=0.8,
        evidence_hash=evidence_hash,
        is_stale=False,
    )


@pytest.mark.asyncio
async def test_database_role_allows_owner_and_invited_engineer(tenant):
    database_id = tenant["database"].id

    ensure_database_role(database_id, tenant["owner"], {"engineer"})
    ensure_database_role(database_id, tenant["invited_engineer"], {"engineer"})


@pytest.mark.asyncio
async def test_database_role_rejects_viewer_for_engineer_and_outsider(tenant):
    database_id = tenant["database"].id

    ensure_database_role(database_id, tenant["viewer"], {"engineer", "viewer"})
    with pytest.raises(HTTPException) as viewer_error:
        ensure_database_role(database_id, tenant["viewer"], {"engineer"})
    assert viewer_error.value.status_code == 403

    for allowed in ({"engineer"}, {"engineer", "viewer"}):
        with pytest.raises(HTTPException) as outsider_error:
            ensure_database_role(database_id, tenant["outsider"], allowed)
        assert outsider_error.value.status_code == 403


@pytest.mark.asyncio
async def test_removed_workspace_routes_return_404(engineer_client):
    assert (await engineer_client.get("/api/v1/workspaces/me")).status_code == 404
    assert (await engineer_client.post("/api/v1/workspaces", json={"name": "Second"})).status_code == 404


@pytest.mark.asyncio
async def test_user_without_databases_gets_empty_list(tenant):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["outsider"].id),
    ) as outsider_client:
        response = await outsider_client.get("/api/v1/databases")
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_databases_include_owned_and_invited_roles(engineer_client, tenant):
    invite = await engineer_client.post(
        f"/api/v1/databases/{tenant['other_database'].id}/members",
        json={"user_id": tenant["owner"].id, "role": "viewer"},
    )
    assert invite.status_code == 403

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["other_owner"].id),
    ) as other_owner_client:
        response = await other_owner_client.post(
            f"/api/v1/databases/{tenant['other_database'].id}/members",
            json={"user_id": tenant["owner"].id, "role": "viewer"},
        )
        assert response.status_code == 200

    response = await engineer_client.get("/api/v1/databases")
    assert response.status_code == 200
    roles = {item["id"]: item["role"] for item in response.json()}
    assert roles == {tenant["database"].id: "engineer", tenant["other_database"].id: "viewer"}


@pytest.mark.asyncio
async def test_database_creation_owner_and_unique_name(engineer_client, tenant):
    created = await engineer_client.post("/api/v1/databases", json={"name": "staging"})
    assert created.status_code == 201
    assert created.json()["role"] == "engineer"
    assert created.json()["owner_id"] == tenant["owner"].id
    assert (await engineer_client.post("/api/v1/databases", json={"name": "staging"})).status_code == 409

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["other_owner"].id),
    ) as other_owner_client:
        same_name = await other_owner_client.post("/api/v1/databases", json={"name": "staging"})
        assert same_name.status_code == 201


@pytest.mark.asyncio
async def test_owner_manages_members_and_member_errors(engineer_client, tenant):
    database_id = tenant["database"].id
    assert (await engineer_client.post(f"/api/v1/databases/{database_id}/members", json={"user_id": tenant["owner"].id, "role": "engineer"})).status_code == 409
    assert (await engineer_client.post(f"/api/v1/databases/{database_id}/members", json={"user_id": 999999999, "role": "viewer"})).status_code == 404

    updated = await engineer_client.post(
        f"/api/v1/databases/{database_id}/members",
        json={"user_id": tenant["viewer"].id, "role": "engineer"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "engineer"
    assert (await engineer_client.delete(f"/api/v1/databases/{database_id}/members/{tenant['outsider'].id}")).status_code == 404

    members = await engineer_client.get(f"/api/v1/databases/{database_id}/members")
    assert members.status_code == 200
    assert {member["user_id"] for member in members.json()} == {tenant["invited_engineer"].id, tenant["viewer"].id}


@pytest.mark.asyncio
async def test_invited_engineer_cannot_manage_members_but_can_create_own_database(tenant):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["invited_engineer"].id),
    ) as invited_client:
        database_id = tenant["database"].id
        assert (await invited_client.get(f"/api/v1/databases/{database_id}/members")).status_code == 403
        assert (await invited_client.post(f"/api/v1/databases/{database_id}/members", json={"user_id": tenant["outsider"].id, "role": "viewer"})).status_code == 403
        assert (await invited_client.delete(f"/api/v1/databases/{database_id}/members/{tenant['viewer'].id}")).status_code == 403
        assert (await invited_client.post("/api/v1/databases", json={"name": "own"})).status_code == 201


@pytest.mark.asyncio
async def test_owner_guards_distinguish_missing_from_other_owner(engineer_client, tenant):
    assert (await engineer_client.get("/api/v1/databases/999999999/members")).status_code == 404
    assert (await engineer_client.get(f"/api/v1/databases/{tenant['other_database'].id}/members")).status_code == 403


@pytest.mark.asyncio
async def test_3c_viewer_cannot_ingest(viewer_client, tenant):
    response = await viewer_client.post("/api/v1/ingest", json={"database_id": tenant["database"].id, "input_path": "unused"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_3c_engineer_can_ingest(engineer_client, tenant):
    response = await engineer_client.post("/api/v1/ingest", json={"database_id": tenant["database"].id, "input_path": "unused"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_3c_outsider_cannot_ingest(outsider_client, tenant):
    response = await outsider_client.post("/api/v1/ingest", json={"database_id": tenant["database"].id, "input_path": "unused"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_3c_viewer_can_chat(viewer_client, tenant, monkeypatch):
    class FakeLLM:
        def invoke(self, _messages):
            return AIMessage(content="DONE")

    monkeypatch.setattr("src.agents.nodes.query_nodes.get_llm", lambda **_kwargs: FakeLLM())
    response = await viewer_client.post("/api/v1/chat", json={"database_id": tenant["database"].id, "question": "lineage?"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_3c_graphs_with_same_table_name_are_isolated(engineer_client, tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    _seed_graph(first, "raw.orders", "a.orders")
    _seed_graph(second, "raw.orders", "b.orders")
    response = await engineer_client.get("/api/v1/graph", params={"database_id": first})
    assert {edge["target_table"] for edge in response.json()["edges"]} == {"a.orders"}


@pytest.mark.asyncio
async def test_3c_graph_read_does_not_leak_other_database(engineer_client, tenant):
    _seed_graph(tenant["other_database"].id, "secret_b", "b.only")
    response = await engineer_client.get("/api/v1/graph", params={"database_id": tenant["database"].id})
    assert "secret_b" not in str(response.json())


def test_3c_review_queue_isolated(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    review_service.add_pending(first, [LineageEdge(source_table="a", target_table="a_pending", confidence=0.5, source_type="llm")])
    review_service.add_pending(second, [LineageEdge(source_table="b", target_table="b_pending", confidence=0.5, source_type="llm")])
    assert [edge.target_table for edge in review_service.list_pending(first)] == ["a_pending"]


@pytest.mark.asyncio
async def test_3c_delete_graph_does_not_clear_other_database(engineer_client, tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    _seed_graph(first, "a", "a_target")
    _seed_graph(second, "b", "b_target")
    assert (await engineer_client.delete("/api/v1/graph", params={"database_id": first})).status_code == 204
    assert graph_service.get_all_tables(second) == ["b", "b_target"]


@pytest.mark.asyncio
async def test_3c_delete_graph_only_clears_alerts_for_its_database(engineer_client, tenant, monkeypatch):
    first = tenant["database"].id
    cleared = []
    monkeypatch.setattr(
        storage_service,
        "clear_breaking_change_alerts",
        lambda database_id, tx=None: cleared.append((database_id, tx)),
    )

    assert (await engineer_client.delete("/api/v1/graph", params={"database_id": first})).status_code == 204

    assert [database_id for database_id, _tx in cleared] == [first]
    assert all(tx is not None for _database_id, tx in cleared)


@pytest.mark.asyncio
async def test_3c_delete_graph_deletes_acknowledged_alerts_only_for_its_database(engineer_client, tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    detection = storage_service.BreakingChangeDetection(
        kind="drop",
        table_name="removed_source",
        new_name=None,
        downstream_tables=["consumer"],
        suggested_action="Restore the reference.",
    )
    storage_service.sync_breaking_change_alerts(first, [detection])
    storage_service.sync_breaking_change_alerts(second, [detection])
    first_alert = storage_service.list_breaking_change_alerts(first, include_acknowledged=True)[0]
    assert storage_service.acknowledge_breaking_change_alert(first, first_alert.id)

    assert (await engineer_client.delete("/api/v1/graph", params={"database_id": first})).status_code == 204

    assert storage_service.list_breaking_change_alerts(first, include_acknowledged=True) == []
    remaining = storage_service.list_breaking_change_alerts(second, include_acknowledged=True)
    assert [(alert.table_name, alert.acknowledged) for alert in remaining] == [("removed_source", False)]


def test_3c_description_queue_isolated(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    item = PendingDescription(node_id=1, table="a", description="a", label="name_only", confidence=0.5, evidence_hash="a", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC))
    description_review_service.add_pending(first, [item])
    assert description_review_service.list_pending(second) == []


def test_3c_column_description_queue_isolated(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    item = PendingColumnDescription(node_id=1, table="a", column="id", description="a", label="name_only", confidence=0.5, evidence_hash="a", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC))
    column_description_review_service.add_pending(first, [item])
    assert column_description_review_service.list_pending(second) == []


def test_3c_node_id_from_other_database_is_not_visible(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    node_id = storage_service.ensure_node(first, "secret_a")
    assert storage_service.load_description_node(second, node_id) is None


def test_3c_clearing_review_queue_is_scoped(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    review_service.add_pending(second, [LineageEdge(source_table="b", target_table="kept", confidence=0.5, source_type="llm")])
    review_service.clear_pending(first)
    assert [edge.target_table for edge in review_service.list_pending(second)] == ["kept"]


def test_3c_graph_registry_is_scoped(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    _seed_graph(first, "only_a", "a_target")
    assert graph_service.get_downstream(second, "only_a") == []


def test_3c_column_descriptions_by_name_do_not_leak_between_databases(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    first_node = storage_service.upsert_nodes(first, [_node_record("stg.orders")])["stg.orders"]
    second_node = storage_service.upsert_nodes(second, [_node_record("stg.orders")])["stg.orders"]
    storage_service.upsert_llm_column_descriptions(
        first, [_column_description(first_node, "First database order id.", "first")], {}, {(first_node, "order_id"): None}
    )
    storage_service.upsert_llm_column_descriptions(
        second, [_column_description(second_node, "Second database order id.", "second")], {}, {(second_node, "order_id"): None}
    )

    first_loaded = storage_service.load_column_descriptions_by_names(first, ["stg.orders"])

    assert first_loaded[("stg.orders", "order_id")].description == "First database order id."
    assert first_loaded[("stg.orders", "order_id")].evidence_hash == "first"
    assert storage_service.load_column_descriptions_by_names(first, []) == {}


@pytest.mark.asyncio
async def test_3c_chat_does_not_leak_other_database_tables(engineer_client, tenant, monkeypatch):
    _seed_graph(tenant["other_database"].id, "secret_b", "b_target")

    class FakeLLM:
        def __init__(self, responses):
            self.responses = iter(responses)

        def invoke(self, _messages):
            return next(self.responses)

    agent = FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "one", "name": "list_relationships", "args": {}, "type": "tool_call"}],
            ),
            AIMessage(content="DONE"),
        ]
    )
    compose = FakeLLM([AIMessage(content="No relationships found.")])
    monkeypatch.setattr(
        "src.agents.nodes.query_nodes.get_llm",
        lambda **kwargs: agent if kwargs.get("tools") else compose,
    )

    response = await engineer_client.post(
        "/api/v1/chat",
        json={"database_id": tenant["database"].id, "question": "list relationships"},
    )

    assert response.status_code == 200
    assert "secret_b" not in response.text


@pytest.mark.asyncio
async def test_3c_cross_database_description_write_returns_404_and_preserves_owner(tenant):
    first, second = tenant["database"].id, tenant["other_database"].id
    node_id = storage_service.ensure_node(first, "secret_a")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["other_owner"].id),
    ) as other_owner_client:
        response = await other_owner_client.put(
            f"/api/v1/descriptions/{node_id}",
            params={"database_id": second},
            json={"description": "must not write"},
        )

    assert response.status_code == 404
    assert storage_service.load_description_node(first, node_id).description is None
