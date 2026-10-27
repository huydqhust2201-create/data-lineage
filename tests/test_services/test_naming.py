import pytest
import sqlglot
from sqlglot import exp

from src.services.naming import (
    normalize_table_name,
    qualified_table_name,
    should_drop_edge,
)


@pytest.mark.parametrize(
    ("name", "dialect", "expected"),
    [
        ('"User"', "postgres", "User"),
        ("Raw.Orders", "postgres", "raw.orders"),
        ('"Raw"."Orders"', "postgres", "Raw.Orders"),
        ("db.raw.orders", "postgres", "db.raw.orders"),
        ('"Raw".orders', "postgres", "Raw.orders"),
        ("Orders", "snowflake", "ORDERS"),
        ("Orders", "mysql", "Orders"),
    ],
)
def test_parser_and_llm_names_use_the_same_rules(name, dialect, expected):
    table = sqlglot.parse_one(name, into=exp.Table, read=dialect)

    assert qualified_table_name(table, dialect) == expected
    assert normalize_table_name(name, dialect) == expected


def test_unquoted_postgres_identifier_is_lowercase():
    assert normalize_table_name("Orders", "postgres") == "orders"


@pytest.mark.parametrize(
    ("source_table", "target_table", "expected_reason"),
    [
        ("raw.orders", "mart.orders", None),
        ("orders", "orders", "lineage self-loop"),
        ("{{ ref('orders') }}", "mart.orders", "unresolved Jinja table reference"),
    ],
)
def test_should_drop_edge(source_table, target_table, expected_reason):
    assert should_drop_edge(source_table, target_table) == expected_reason
