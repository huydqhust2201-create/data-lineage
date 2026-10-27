from pathlib import Path

import pytest

from src.services.parser_service import SQLParserService

MODELS_DIR = Path("samples/jaffle-shop/models")
EDGE_MODEL_PATHS = [
    "marts/customers.sql",
    "marts/metricflow_time_spine.sql",
    "marts/order_items.sql",
    "marts/orders.sql",
    "staging/stg_customers.sql",
    "staging/stg_locations.sql",
    "staging/stg_order_items.sql",
    "staging/stg_orders.sql",
    "staging/stg_products.sql",
    "staging/stg_supplies.sql",
]


@pytest.fixture
def parser_service():
    return SQLParserService(default_dialect="postgres")


@pytest.mark.parametrize("relative_path", EDGE_MODEL_PATHS)
def test_dbt_column_lineage_targets_model_file_stem(parser_service, relative_path):
    path = MODELS_DIR / relative_path

    edges = parser_service.parse_file(str(path))

    assert edges
    assert {edge.target_table for edge in edges} == {path.stem}


def test_staging_models_do_not_merge_into_renamed_cte(parser_service):
    paths = sorted((MODELS_DIR / "staging").glob("*.sql"))
    targets = {
        edge.target_table
        for path in paths
        for edge in parser_service.parse_file(str(path))
    }

    assert targets == {path.stem for path in paths}
    assert "renamed" not in targets


def test_jaffle_shop_contains_raw_orders_to_staging_to_mart_chain(parser_service):
    edges = parser_service.parse_directory(str(MODELS_DIR))
    table_pairs = {(edge.source_table, edge.target_table) for edge in edges}

    assert ("ecom.raw_orders", "stg_orders") in table_pairs
    assert ("stg_orders", "orders") in table_pairs


def test_stg_orders_preserves_expected_column_lineage(parser_service):
    edges = parser_service.parse_file(str(MODELS_DIR / "staging/stg_orders.sql"))

    assert {
        (edge.source_table, edge.source_column, edge.target_table, edge.target_column)
        for edge in edges
    } == {
        ("ecom.raw_orders", "id", "stg_orders", "order_id"),
        ("ecom.raw_orders", "store_id", "stg_orders", "location_id"),
        ("ecom.raw_orders", "customer", "stg_orders", "customer_id"),
        ("ecom.raw_orders", "subtotal", "stg_orders", "subtotal_cents"),
        ("ecom.raw_orders", "tax_paid", "stg_orders", "tax_paid_cents"),
        ("ecom.raw_orders", "order_total", "stg_orders", "order_total_cents"),
    }


@pytest.mark.parametrize(
    ("model_name", "source_table"),
    [
        ("locations", "stg_locations"),
        ("products", "stg_products"),
        ("supplies", "stg_supplies"),
    ],
)
def test_dbt_passthrough_model_emits_one_table_level_edge(parser_service, model_name, source_table):
    edges = parser_service.parse_file(str(MODELS_DIR / f"marts/{model_name}.sql"))

    assert len(edges) == 1
    edge = edges[0]
    assert (edge.source_table, edge.target_table) == (source_table, model_name)
    assert edge.source_column is None
    assert edge.target_column is None
    assert edge.transform_type == "unknown"
    assert edge.confidence == 1.0
    assert edge.source_type == "parser"


def test_full_jaffle_shop_parse_has_complete_model_graph(parser_service):
    # Bài test này về ĐỒ THỊ PHỤ THUỘC MODEL (data lineage) — bỏ qua cạnh
    # control lineage (WHERE/JOIN/GROUP BY), vốn là 1 chiều bổ sung.
    edges = [e for e in parser_service.parse_directory(str(MODELS_DIR)) if e.dependency_kind == "output"]
    pairs = {}
    for edge in edges:
        key = (edge.source_table, edge.target_table)
        pairs[key] = pairs.get(key, 0) + 1

    nodes = {source for source, _ in pairs} | {target for _, target in pairs}
    in_degree = {node: sum(count for (_, target), count in pairs.items() if target == node) for node in nodes}

    assert len(nodes) == 20
    assert sum(pairs.values()) == 45
    assert {edge.target_table for edge in edges} >= {path.stem for path in MODELS_DIR.rglob("*.sql")}
    assert {node for node, degree in in_degree.items() if degree == 0} == {
        "days",
        "ecom.raw_customers",
        "ecom.raw_items",
        "ecom.raw_orders",
        "ecom.raw_products",
        "ecom.raw_stores",
        "ecom.raw_supplies",
    }
