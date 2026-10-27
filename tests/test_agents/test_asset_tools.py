import os
from datetime import UTC, datetime, timedelta

import networkx as nx
import psycopg2
import pytest

from src.agents.tools.asset_tools import GetAssetCapability, GetAssetParams
from src.config import get_settings
from src.models.schemas import LineageEdge
from src.services import review_service, storage_service


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


# clean_asset_data (dưới) xóa sạch lineage_edges/lineage_nodes trên chính
# DATABASE_URL đang cấu hình — xem giải thích đầy đủ ở test_storage_service.py.
# Đã từng thật sự xóa mất dữ liệu demo của 1 dev, mặc định SKIP để không lặp lại.
_DB_WIPE_ALLOWED = os.environ.get("PYTEST_ALLOW_DB_WIPE") == "1"

pytestmark = pytest.mark.skipif(
    not _postgres_available() or not _DB_WIPE_ALLOWED,
    reason="Test này xóa sạch lineage_edges/lineage_nodes trên DATABASE_URL đang cấu hình. "
    "SKIP theo mặc định để tránh vô tình xóa dữ liệu dev/demo thật. Set PYTEST_ALLOW_DB_WIPE=1 "
    "chỉ khi chắc chắn DATABASE_URL đang trỏ tới Postgres test/disposable, không phải Postgres dev.",
)


@pytest.fixture(autouse=True)
def clean_asset_data(database_id):
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)
    review_service._reset()
    yield
    storage_service.save(database_id, nx.MultiDiGraph())
    storage_service.clear_nodes(database_id)
    review_service._reset()


def _node(name: str, *, defined_in: str | None = "models/orders.sql") -> storage_service.NodeRecord:
    return storage_service.NodeRecord(
        current_name=name,
        defined_in=defined_in,
        source_file=None,
        columns_produced=["order_id"],
        columns_consumed=["raw_id"],
        upstream_tables=["raw.orders"],
        downstream_tables=["mart.orders"],
        source_types=["parser"],
        transform_types=["direct"],
        confidence_min=0.8,
        confidence_max=1.0,
    )


def _seed(database_id: int, name: str, when: datetime, *, defined_in: str | None = "models/orders.sql") -> int:
    node_id = storage_service.upsert_nodes(database_id, [_node(name, defined_in=defined_in)])[name]
    storage_service.append_node_events(database_id, [storage_service.NodeEvent(node_id, "modified", when)])
    return node_id


def test_get_asset_returns_profiles_for_a_batch_in_one_capability_call(database_id):
    capability = GetAssetCapability()
    start = datetime(2026, 8, 10, tzinfo=UTC)
    for index, name in enumerate(["raw.orders", "stg.orders", "mart.orders"]):
        _seed(database_id, name, start + timedelta(days=index))

    result = capability.run(GetAssetParams(tables=["raw.orders", "stg.orders", "mart.orders"]), database_id)

    assert result.error is None
    assert [asset.name for asset in result.extra["assets"]] == ["raw.orders", "stg.orders", "mart.orders"]
    assert result.confirmed == []
    assert result.pending == []
    assert result.extra["skipped"] == []


def test_get_asset_skips_ambiguous_name_without_losing_valid_profiles(database_id):
    timestamp = datetime(2026, 8, 10, tzinfo=UTC)
    for name in ["raw.orders", "mart.orders", "stg.customers", "mart.customers"]:
        _seed(database_id, name, timestamp)

    result = GetAssetCapability().run(GetAssetParams(tables=["orders", "stg.customers", "mart.customers"]), database_id)

    assert result.error is None
    assert [asset.name for asset in result.extra["assets"]] == ["stg.customers", "mart.customers"]
    assert result.extra["skipped"] == [{"mention": "orders", "reason": "ambiguous"}]


def test_get_asset_soft_truncates_large_batch(database_id):
    timestamp = datetime(2026, 8, 10, tzinfo=UTC)
    names = [f"model_{index}" for index in range(25)]
    for name in names:
        _seed(database_id, name, timestamp)

    result = GetAssetCapability().run(GetAssetParams(tables=names), database_id)

    assert len(result.extra["assets"]) == 20
    assert result.extra["truncated"] is True


def test_get_asset_reads_dropped_history_and_includes_old_names_in_vocabulary(database_id):
    timestamp = datetime(2026, 8, 10, tzinfo=UTC)
    node_id = storage_service.ensure_node(database_id, "stg.orders")
    assert storage_service.rename_node_by_id(database_id, node_id, "mart.orders")
    storage_service.append_node_events(database_id,
        [storage_service.NodeEvent(node_id, "rename", timestamp, {"from": "stg.orders", "to": "mart.orders"})]
    )
    assert storage_service.mark_dropped(database_id, node_id, timestamp + timedelta(days=1))
    storage_service.append_node_events(database_id, [storage_service.NodeEvent(node_id, "drop", timestamp + timedelta(days=1))])

    result = GetAssetCapability().run(GetAssetParams(tables=["mart.orders"]), database_id)
    asset = result.extra["assets"][0]

    assert asset.is_dropped is True
    assert asset.dropped_at == (timestamp + timedelta(days=1)).isoformat()
    assert asset.previous_names == [{"name": "stg.orders", "changed_at": timestamp.isoformat()}]
    assert {"stg.orders", "mart.orders"} <= GetAssetCapability().vocabulary(result)


def test_get_asset_template_orders_latest_first_and_pending_count_is_live(database_id):
    timestamp = datetime(2026, 8, 10, tzinfo=UTC)
    _seed(database_id, "old", timestamp)
    _seed(database_id, "new", timestamp + timedelta(days=1))
    storage_service.upsert_nodes(database_id, [_node("unknown", defined_in=None)])
    edge = LineageEdge(source_table="old", target_table="new", confidence=0.5, source_type="llm")
    review_service.add_pending(database_id, [edge])
    capability = GetAssetCapability()

    result = capability.run(GetAssetParams(tables=["old", "new", "unknown"]), database_id)

    by_name = {asset.name: asset for asset in result.extra["assets"]}
    assert by_name["old"].pending_count == 1
    assert by_name["new"].pending_count == 1
    assert capability.template(result).splitlines()[0].startswith("new:")
    assert "unknown: không rõ thời điểm thay đổi" in capability.template(result)
    review_service.pop_pending(database_id, edge.edge_id)
    assert capability.run(GetAssetParams(tables=["old"]), database_id).extra["assets"][0].pending_count == 0
