"""Phase 5 description-flow tests; LLM and TEI are always mocked."""

from contextlib import contextmanager
from datetime import UTC, datetime

import networkx as nx
import pytest
from fastapi import HTTPException

from src.agents.nodes import lineage_nodes
from src.config import get_settings
from src.models.schemas import DescriptionUpdateRequest, PendingColumnDescription, PendingDescription
from src.services import (
    column_description_review_service,
    description_review_service,
    description_service,
    embedding_service,
    graph_service,
    storage_service,
)


def _node(description=None):
    record = storage_service.NodeRecord(
        current_name="standalone.orders",
        defined_in="models/orders.sql",
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
    return storage_service.DescriptionNode(1, record, description, datetime(2026, 8, 18, tzinfo=UTC))


def _node_with_column(description=None):
    record = storage_service.NodeRecord(
        current_name="standalone.orders",
        defined_in="models/orders.sql",
        source_file=None,
        columns_produced=["order_id"],
        columns_consumed=[],
        upstream_tables=[],
        downstream_tables=[],
        source_types=[],
        transform_types=[],
        confidence_min=None,
        confidence_max=None,
    )
    return storage_service.DescriptionNode(1, record, description, datetime(2026, 8, 18, tzinfo=UTC))


@pytest.fixture(autouse=True)
def _reset_pending_and_settings():
    description_review_service._reset()
    column_description_review_service._reset()
    graph_service._reset_graph(1, nx.MultiDiGraph())
    get_settings.cache_clear()
    yield
    description_review_service._reset()
    column_description_review_service._reset()
    graph_service._reset_graph(1, None)
    get_settings.cache_clear()


def _fake_transaction(monkeypatch):
    @contextmanager
    def transaction():
        yield object()

    monkeypatch.setattr(storage_service, "transaction", transaction)


def test_describe_node_hashes_db_payload_but_sends_ddl_to_llm(monkeypatch, tmp_path, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    sql_path = tmp_path / "models"
    sql_path.mkdir()
    (sql_path / "orders.sql").write_text("CREATE TABLE standalone.orders (id INT)", encoding="utf-8")
    captured = {}
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node()])
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [1],
    )
    monkeypatch.setattr(storage_service, "mark_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_tables",
        lambda payloads: (
            captured.update(payloads)
            or {"1": description_service.RawDescription(description="Orders.", label="documented")}
        ),
    )

    result = lineage_nodes.describe_node({"input_path": str(tmp_path), "database_id": database_id})

    prompt_payload = captured["1"]
    assert "CREATE TABLE standalone.orders" in prompt_payload["ddl"]
    assert "ddl" not in description_service.build_evidence_payload(_node(), {})
    assert result == {"descriptions_written": 1, "descriptions_pending": 0}
    assert writes[0].evidence_hash == description_service.evidence_hash(
        description_service.build_evidence_payload(_node(), {})
    )


def test_describe_node_low_confidence_enqueues_without_db_write(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node()])
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("TEI must not embed pending proposal"))
    monkeypatch.setattr(storage_service, "upsert_llm_descriptions", lambda *args: pytest.fail("must not write pending"))
    monkeypatch.setattr(storage_service, "mark_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_tables",
        lambda _payloads: {"1": description_service.RawDescription(description="Maybe orders.", label="name_only")},
    )

    assert lineage_nodes.describe_node({"input_path": "/missing", "database_id": database_id}) == {
        "descriptions_written": 0,
        "descriptions_pending": 1,
    }
    assert description_review_service.list_pending(database_id, )[0].label == "name_only"


def test_describe_node_disabled_does_not_call_services(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: pytest.fail("must not load"))

    assert lineage_nodes.describe_node({"input_path": "/unused", "database_id": database_id}) == {
        "descriptions_written": 0,
        "descriptions_pending": 0,
    }


def test_changed_llm_description_is_rewritten_without_human_review(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    existing = storage_service.DescriptionRecord(1, "Old.", "llm", "documented", 0.9, "old-hash", False)
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node(existing)])
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [1],
    )
    monkeypatch.setattr(storage_service, "mark_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_tables",
        lambda _payloads: {"1": description_service.RawDescription(description="New.", label="documented")},
    )

    assert lineage_nodes.describe_node({"input_path": "/missing", "database_id": database_id}) == {
        "descriptions_written": 1,
        "descriptions_pending": 0,
    }
    assert writes[0].description == "New."
    assert description_review_service.list_pending(database_id, ) == []


def test_written_description_replaces_outdated_pending_item(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    _fake_transaction(monkeypatch)
    description_review_service.add_pending(database_id,
        [
            PendingDescription(
                node_id=1,
                table="standalone.orders",
                description="Old proposal.",
                label="name_only",
                confidence=0.3,
                evidence_hash="old-hash",
                created_at=datetime.now(UTC),
            )
        ]
    )
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node()])
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(storage_service, "upsert_llm_descriptions", lambda *args: [1])
    monkeypatch.setattr(storage_service, "mark_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_tables",
        lambda _payloads: {"1": description_service.RawDescription(description="New proposal.", label="documented")},
    )

    lineage_nodes.describe_node({"input_path": "/missing", "database_id": database_id})

    assert description_review_service.list_pending(database_id, ) == []


@pytest.mark.asyncio
async def test_description_confirm_reject_and_put_routes(monkeypatch, database_id):
    from src.api import routes

    current = _node()
    description_review_service.add_pending(database_id,
        [
            PendingDescription(
                node_id=1,
                table="standalone.orders",
                description="LLM orders.",
                label="schema_inferred",
                confidence=0.75,
                evidence_hash="proposal-hash",
                created_at=datetime.now(UTC),
            )
        ]
    )
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])
    monkeypatch.setattr(storage_service, "confirm_pending_description", lambda *args: True)

    confirmed = await routes.confirm_pending_description(1, database_id)
    assert confirmed.evidence_hash == "proposal-hash"
    with pytest.raises(HTTPException) as exc:
        await routes.reject_pending_description(1, database_id)
    assert exc.value.status_code == 404

    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [current])
    monkeypatch.setattr(storage_service, "put_human_description", lambda *args: True)
    await routes.put_description(1, DescriptionUpdateRequest(description="Human orders."), database_id)


@pytest.mark.asyncio
async def test_description_endpoints_are_exercised_over_http(client, monkeypatch, database_id):
    current = _node()
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [current])
    monkeypatch.setattr(storage_service, "confirm_pending_description", lambda *args: True)
    monkeypatch.setattr(storage_service, "put_human_description", lambda *args: True)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])
    item = PendingDescription(
        node_id=1,
        table="standalone.orders",
        description="LLM orders.",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash="proposal-hash",
        created_at=datetime.now(UTC),
    )
    description_review_service.add_pending(database_id, [item])

    assert (await client.get("/api/v1/descriptions/pending", params={"database_id": database_id})).json()[0]["node_id"] == 1
    assert (await client.post("/api/v1/descriptions/1/confirm", params={"database_id": database_id})).status_code == 200
    description_review_service.add_pending(database_id, [item])
    assert (await client.post("/api/v1/descriptions/1/reject", params={"database_id": database_id})).status_code == 204
    assert (await client.put("/api/v1/descriptions/1", params={"database_id": database_id}, json={"description": "Human orders."})).status_code == 200


@pytest.mark.asyncio
async def test_confirm_returns_409_and_restores_pending_item_over_http(client, monkeypatch, database_id):
    current = _node()
    item = PendingDescription(
        node_id=1,
        table="standalone.orders",
        description="Proposal based on old evidence.",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash="old-hash",
        created_at=datetime.now(UTC),
        base_source="human",
        base_hash="old-hash",
    )
    description_review_service.add_pending(database_id, [item])
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(storage_service, "confirm_pending_description", lambda *args: False)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])

    response = await client.post("/api/v1/descriptions/1/confirm", params={"database_id": database_id})

    assert response.status_code == 409
    assert (await client.get("/api/v1/descriptions/pending", params={"database_id": database_id})).json()[0]["evidence_hash"] == "old-hash"


def test_stale_human_description_stays_locked_and_enqueues_comparison(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    human = storage_service.DescriptionRecord(1, "Human-written description.", "human", None, None, "old-hash", False)
    marked = []
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node(human)])
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("stale proposal must not embed"))
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [],
    )
    monkeypatch.setattr(
        storage_service,
        "mark_descriptions_stale",
        lambda _database_id, node_ids, expected_hash, tx: marked.append((node_ids, expected_hash)),
    )
    monkeypatch.setattr(
        description_service,
        "describe_tables",
        lambda _payloads: {"1": description_service.RawDescription(description="Fresh proposal.", label="documented")},
    )

    result = lineage_nodes.describe_node({"input_path": "/missing", "database_id": database_id})

    [pending] = description_review_service.list_pending(database_id, )
    assert result == {"descriptions_written": 0, "descriptions_pending": 1}
    assert writes == []
    assert marked == [([1], {1: "old-hash"})]
    assert pending.is_stale_proposal is True
    assert pending.current_description == "Human-written description."
    assert pending.base_source == "human"
    assert pending.base_hash == "old-hash"


def test_describe_columns_node_hashes_db_payload_but_sends_ddl_to_llm(monkeypatch, tmp_path, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    sql_path = tmp_path / "models"
    sql_path.mkdir()
    (sql_path / "orders.sql").write_text("CREATE TABLE standalone.orders (id INT)", encoding="utf-8")
    captured = {}
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node_with_column()])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *_args: {})
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_column_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [(1, "order_id")],
    )
    monkeypatch.setattr(storage_service, "mark_column_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_columns",
        lambda payloads: (
            captured.update(payloads)
            or {"1:order_id": description_service.RawDescription(description="Order id.", label="documented")}
        ),
    )

    result = lineage_nodes.describe_columns_node({"input_path": str(tmp_path), "database_id": database_id})

    prompt_payload = captured["1:order_id"]
    assert "CREATE TABLE standalone.orders" in prompt_payload["ddl"]
    assert "ddl" not in description_service.build_column_evidence_payload(1, "standalone.orders", "order_id")
    assert result == {"column_descriptions_written": 1, "column_descriptions_pending": 0}
    assert writes[0].evidence_hash == description_service.evidence_hash(
        description_service.build_column_evidence_payload(1, "standalone.orders", "order_id")
    )


def test_describe_columns_node_low_confidence_enqueues_without_db_write(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node_with_column()])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *_args: {})
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("TEI must not embed pending proposal"))
    monkeypatch.setattr(
        storage_service, "upsert_llm_column_descriptions", lambda *args: pytest.fail("must not write pending")
    )
    monkeypatch.setattr(storage_service, "mark_column_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_columns",
        lambda _payloads: {"1:order_id": description_service.RawDescription(description="Maybe id.", label="name_only")},
    )

    assert lineage_nodes.describe_columns_node({"input_path": "/missing", "database_id": database_id}) == {
        "column_descriptions_written": 0,
        "column_descriptions_pending": 1,
    }
    assert column_description_review_service.list_pending(database_id, )[0].label == "name_only"


def test_describe_columns_node_disabled_does_not_call_services(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: pytest.fail("must not load"))

    assert lineage_nodes.describe_columns_node({"input_path": "/unused", "database_id": database_id}) == {
        "column_descriptions_written": 0,
        "column_descriptions_pending": 0,
    }


def test_changed_llm_column_description_is_rewritten_without_human_review(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    existing = storage_service.ColumnDescriptionRecord(1, "order_id", "Old.", "llm", "documented", 0.9, "old-hash", False)
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node_with_column()])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *_args: {(1, "order_id"): existing})
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_column_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [(1, "order_id")],
    )
    monkeypatch.setattr(storage_service, "mark_column_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_columns",
        lambda _payloads: {"1:order_id": description_service.RawDescription(description="New.", label="documented")},
    )

    assert lineage_nodes.describe_columns_node({"input_path": "/missing", "database_id": database_id}) == {
        "column_descriptions_written": 1,
        "column_descriptions_pending": 0,
    }
    assert writes[0].description == "New."
    assert column_description_review_service.list_pending(database_id, ) == []


def test_written_column_description_replaces_outdated_pending_item(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    _fake_transaction(monkeypatch)
    column_description_review_service.add_pending(database_id,
        [
            PendingColumnDescription(
                node_id=1,
                table="standalone.orders",
                column="order_id",
                description="Old proposal.",
                label="name_only",
                confidence=0.3,
                evidence_hash="old-hash",
                created_at=datetime.now(UTC),
            )
        ]
    )
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node_with_column()])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *_args: {})
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [[1.0] * 1024])
    monkeypatch.setattr(storage_service, "upsert_llm_column_descriptions", lambda *args: [(1, "order_id")])
    monkeypatch.setattr(storage_service, "mark_column_descriptions_stale", lambda *args: None)
    monkeypatch.setattr(
        description_service,
        "describe_columns",
        lambda _payloads: {
            "1:order_id": description_service.RawDescription(description="New proposal.", label="documented")
        },
    )

    lineage_nodes.describe_columns_node({"input_path": "/missing", "database_id": database_id})

    assert column_description_review_service.list_pending(database_id, ) == []


def test_stale_human_column_description_stays_locked_and_enqueues_comparison(monkeypatch, database_id):
    monkeypatch.setenv("DESCRIPTION_ENABLED", "true")
    get_settings.cache_clear()
    human = storage_service.ColumnDescriptionRecord(1, "order_id", "Human-written.", "human", None, None, "old-hash", False)
    marked = []
    writes = []
    _fake_transaction(monkeypatch)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [_node_with_column()])
    monkeypatch.setattr(storage_service, "load_column_descriptions", lambda *_args: {(1, "order_id"): human})
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: pytest.fail("stale proposal must not embed"))
    monkeypatch.setattr(
        storage_service,
        "upsert_llm_column_descriptions",
        lambda _database_id, records, embeddings, expected, tx: writes.extend(records) or [],
    )
    monkeypatch.setattr(
        storage_service,
        "mark_column_descriptions_stale",
        lambda _database_id, keys, expected_hash, tx: marked.append((keys, expected_hash)),
    )
    monkeypatch.setattr(
        description_service,
        "describe_columns",
        lambda _payloads: {
            "1:order_id": description_service.RawDescription(description="Fresh proposal.", label="documented")
        },
    )

    result = lineage_nodes.describe_columns_node({"input_path": "/missing", "database_id": database_id})

    [pending] = column_description_review_service.list_pending(database_id, )
    assert result == {"column_descriptions_written": 0, "column_descriptions_pending": 1}
    assert writes == []
    assert marked == [([(1, "order_id")], {(1, "order_id"): "old-hash"})]
    assert pending.is_stale_proposal is True
    assert pending.current_description == "Human-written."
    assert pending.base_source == "human"
    assert pending.base_hash == "old-hash"


@pytest.mark.asyncio
async def test_column_description_confirm_reject_and_put_routes(monkeypatch, database_id):
    from src.api import routes

    current = _node_with_column()
    column_description_review_service.add_pending(database_id,
        [
            PendingColumnDescription(
                node_id=1,
                table="standalone.orders",
                column="order_id",
                description="LLM order id.",
                label="schema_inferred",
                confidence=0.75,
                evidence_hash="proposal-hash",
                created_at=datetime.now(UTC),
            )
        ]
    )
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])
    monkeypatch.setattr(storage_service, "confirm_pending_column_description", lambda *args: True)

    confirmed = await routes.confirm_pending_column_description(1, "order_id", database_id)
    assert confirmed.evidence_hash == "proposal-hash"
    with pytest.raises(HTTPException) as exc:
        await routes.reject_pending_column_description(1, "order_id", database_id)
    assert exc.value.status_code == 404

    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [current])
    monkeypatch.setattr(storage_service, "put_human_column_description", lambda *args: True)
    await routes.put_column_description(1, "order_id", DescriptionUpdateRequest(description="Human order id."), database_id)


@pytest.mark.asyncio
async def test_column_description_endpoints_are_exercised_over_http(client, monkeypatch, database_id):
    current = _node_with_column()
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(storage_service, "load_live_nodes_for_description", lambda *_args: [current])
    monkeypatch.setattr(storage_service, "confirm_pending_column_description", lambda *args: True)
    monkeypatch.setattr(storage_service, "put_human_column_description", lambda *args: True)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])
    item = PendingColumnDescription(
        node_id=1,
        table="standalone.orders",
        column="order_id",
        description="LLM order id.",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash="proposal-hash",
        created_at=datetime.now(UTC),
    )
    column_description_review_service.add_pending(database_id, [item])

    assert (await client.get("/api/v1/column-descriptions/pending", params={"database_id": database_id})).json()[0]["node_id"] == 1
    assert (await client.post("/api/v1/column-descriptions/1/order_id/confirm", params={"database_id": database_id})).status_code == 200
    column_description_review_service.add_pending(database_id, [item])
    assert (await client.post("/api/v1/column-descriptions/1/order_id/reject", params={"database_id": database_id})).status_code == 204
    assert (
        await client.put("/api/v1/column-descriptions/1/order_id", params={"database_id": database_id}, json={"description": "Human order id."})
    ).status_code == 200


@pytest.mark.asyncio
async def test_column_confirm_returns_409_and_restores_pending_item_over_http(client, monkeypatch, database_id):
    current = _node_with_column()
    item = PendingColumnDescription(
        node_id=1,
        table="standalone.orders",
        column="order_id",
        description="Proposal based on old evidence.",
        label="schema_inferred",
        confidence=0.75,
        evidence_hash="old-hash",
        created_at=datetime.now(UTC),
        base_source="human",
        base_hash="old-hash",
    )
    column_description_review_service.add_pending(database_id, [item])
    monkeypatch.setattr(storage_service, "load_description_node", lambda *_args: current)
    monkeypatch.setattr(storage_service, "confirm_pending_column_description", lambda *args: False)
    monkeypatch.setattr(embedding_service, "embed", lambda _texts: [])

    response = await client.post("/api/v1/column-descriptions/1/order_id/confirm", params={"database_id": database_id})

    assert response.status_code == 409
    assert (await client.get("/api/v1/column-descriptions/pending", params={"database_id": database_id})).json()[0]["evidence_hash"] == "old-hash"
