import networkx as nx
import pytest

from src.agents.chat import guard
from src.agents.tools.ddl_preview_tools import PREVIEW_DDL_IMPACT_CAPABILITY, PreviewDdlImpactParams
from src.models.schemas import LineageEdge
from src.services import ddl_preview_service, graph_service


@pytest.fixture(autouse=True)
def fresh_graph():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(1, None)


def add_edge(source, target, source_column="id", target_column="id"):
    graph_service.add_edge(1,
        LineageEdge(
            source_table=source,
            source_column=source_column,
            target_table=target,
            target_column=target_column,
            confidence=1.0,
            source_type="parser",
        )
    )


def test_empty_graph_and_unparsed_sql_are_capability_errors():
    assert PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="DROP TABLE a;"), 1).error == "graph_is_empty"

    add_edge("raw.a", "a")
    assert (
        PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="THIS IS NOT VALID SQL (((;"), 1).error
        == "sql_unparsed"
    )


def test_preview_payload_is_redacted_and_vocabulary_allows_real_names_and_columns():
    add_edge("raw.a", "a", "id", "a_id")
    result = PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="ALTER TABLE a RENAME TO b; DROP TABLE raw.a;"), 1)
    payload = result.extra["ddl_preview"]
    vocabulary = PREVIEW_DDL_IMPACT_CAPABILITY.vocabulary(result)

    assert set(payload) == {
        "statements",
        "removed_edges",
        "orphaned_tables",
        "unknown_tables",
        "rename_conflicts",
        "unsupported_statements_count",
        "risk_by_statement",
        "edges_before",
        "edges_after",
        "tables_before",
        "tables_after",
    }
    assert "sql" not in str(payload)
    assert {"a", "b", "raw.a", "id", "a_id"} <= vocabulary
    assert guard.unknown_mentions("raw.a.id would be removed from a.a_id", {"ddl_preview": payload}, vocabulary) == []
    assert result.confirmed == []
    assert result.pending == []


def test_preview_payload_keeps_statement_risk_columns():
    add_edge("raw.a", "a", "id", "a_id")

    result = PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="DROP TABLE raw.a;"), 1)

    (group,) = result.extra["ddl_preview"]["risk_by_statement"]
    assert group["change_kind"] == "drop_table"
    assert group["risks"] == [
        {
            "source_table": "raw.a",
            "source_column": "id",
            "target_table": "a",
            "target_column": "a_id",
            "risk": group["risks"][0]["risk"],
        }
    ]


def test_preview_unavailable_is_contained(monkeypatch):
    add_edge("raw.a", "a")
    monkeypatch.setattr(ddl_preview_service, "preview", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError()))

    result = PREVIEW_DDL_IMPACT_CAPABILITY.run(PreviewDdlImpactParams(sql="DROP TABLE raw.a;"), 1)

    assert result.error == "preview_unavailable"
