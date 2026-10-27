import networkx as nx
import pytest

from src.agents.chat import resolve
from src.models.schemas import LineageEdge
from src.services import graph_service, review_service


@pytest.fixture(autouse=True)
def fresh_lineage():
    graph_service._reset_graph(1, nx.MultiDiGraph())
    review_service._reset()
    yield
    graph_service._reset_graph(1, None)
    review_service._reset()


@pytest.mark.parametrize(
    "mention,candidates,expected",
    [
        ("ecom.orders", ["ecom.orders"], "ecom.orders"),
        ("ECOM.Orders", ["ecom.orders"], "ecom.orders"),
        ("customers", ["raw.customers"], "raw.customers"),
        ("public.customers", ["raw.customers"], "raw.customers"),
        ("orders", ["orders", "ecom.orders", "stg.orders"], "orders"),
    ],
)
def test_resolve_table_prefers_exact_matches(mention, candidates, expected):
    result = resolve.resolve_table(mention, candidates)
    assert result.status == "resolved"
    assert result.table == expected


def test_resolve_table_returns_ambiguity_and_suggestions():
    ambiguous = resolve.resolve_table("orders", ["ecom.orders", "stg.orders"])
    missing = resolve.resolve_table("raw.customerz", ["raw.customers"])
    assert ambiguous.candidates == ["ecom.orders", "stg.orders"]
    assert missing.suggestions == ["raw.customers"]


def test_known_tables_includes_pending_only_table():
    review_service.add_pending(1,
        [LineageEdge(source_table="stg.orders", target_table="legacy_ltv", confidence=0.5, source_type="llm")]
    )
    assert "legacy_ltv" in resolve.known_tables(1)


def test_resolve_column_uses_normalized_real_column():
    graph_service.add_edge(1,
        LineageEdge(
            source_table="ecom.orders",
            source_column="order_id",
            target_table="stg.orders",
            confidence=1.0,
            source_type="parser",
        )
    )
    assert resolve.resolve_column(1, "ecom.orders", "ORDER_ID") == "order_id"
    assert resolve.resolve_column(1, "ecom.orders", "missing") is None


@pytest.mark.parametrize(
    "reply,expected",
    [("2", "stg.orders"), ("Stg.Orders", "stg.orders"), ("please use stg.orders", "stg.orders"), ("new topic", None)],
)
def test_match_clarification_returns_only_listed_candidate(reply, expected):
    candidates = ["ecom.orders", "stg.orders"]
    result = resolve.match_clarification(reply, candidates)
    assert result == expected
    assert result in {*candidates, None}


def test_match_clarification_only_accepts_short_selections_or_single_confirmation():
    assert resolve.match_clarification("revenue_alerts_staging ảnh hưởng tới bảng nào vậy nhỉ", ["revenue_alerts_staging"]) is None
    assert resolve.match_clarification("ừ", ["revenue_alerts_staging"]) == "revenue_alerts_staging"
    assert resolve.match_clarification("ừ", ["revenue_alerts_staging", "revenue_alerts_final"]) is None


# Bo ca DUNG CHUNG voi ban TypeScript o frontend/src/utils/linkifyEntities.test.ts.
# Mot hop dong "khop tron dinh danh", hai ban cai dat (Python o day, TS o frontend) —
# khong the dung chung mot regex giua hai runtime, nen phai co test doi chieu de hai
# ban khong troi lech nhau. Sua mot ben ma quen ben kia thi chat linkify mot ten trong
# khi backend khong tu go cho chinh ten do.
@pytest.mark.parametrize(
    "text,name,expected",
    [
        ("làm thế nào để 1 doctor được đánh dấu là underperforming_doctors?", "underperforming_doctors", True),
        ("làm thế nào để 1 doctor được đánh dấu là underperforming_doctors?", "doctor_workload", False),
        ("doctor_workloads là gì?", "doctor_workload", False),
        ("`revenue_alerts_final` lấy dữ liệu từ đâu?", "revenue_alerts_final", True),
        ("revenue_alerts_finalized", "revenue_alerts_final", False),
        ("REVENUE_ALERTS_FINAL có gì?", "revenue_alerts_final", True),
        ("nothing to link", "revenue_alerts_final", False),
        ("ecom.orders và stg.orders", "stg.orders", True),
    ],
)
def test_mentions_identifier_matches_the_typescript_boundary_rule(text, name, expected):
    assert resolve.mentions_identifier(text, name) is expected


def test_question_with_choice_shares_the_same_boundary_rule():
    # Cung dinh nghia bien: mention ngan nam trong mot dinh danh dai hon thi KHONG bi thay.
    assert (
        resolve.question_with_choice("so sánh revenue_alert và revenue_alerts_staging", "revenue_alert", "revenue_alerts_final")
        == "so sánh revenue_alerts_final và revenue_alerts_staging"
    )
    assert resolve.question_with_choice("không có tên đó", "revenue_alert", "x") == "không có tên đó"
    assert resolve.question_with_choice("bất kỳ câu nào", "", "x") == "bất kỳ câu nào"
