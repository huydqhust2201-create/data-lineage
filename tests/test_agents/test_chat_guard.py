import pytest

from src.agents.chat.guard import TABLE_TOKEN, unknown_mentions


@pytest.fixture
def facts():
    return {
        "confirmed": [{"evidence_file": "models/orders.sql", "source_type": "parser"}],
        "inferred_pending": [{"evidence": {"file_path": "dbt_project/models/legacy.sql"}, "confidence": 0.5}],
    }


@pytest.mark.parametrize(
    "answer",
    [
        "Fct_sales phụ thuộc ecom.orders",
        "STG.ORDERS là bảng trung gian",
        "confidence và source_type là dữ kiện hợp lệ",
        "Bằng chứng models/orders.sql đã được ghi nhận",
        "Nguồn dbt_project/models/legacy.sql đang chờ duyệt",
    ],
)
def test_guard_accepts_vocabulary_payload_keys_and_evidence(answer, facts):
    assert unknown_mentions(answer, facts, {"ecom.orders", "stg.orders", "fct_sales"}) == []


@pytest.mark.parametrize("answer", ["mart.ghost_table", "Mart.Ghost_Table", "raw.orders_backup"])
def test_guard_rejects_unknown_dotted_table_like_mentions(answer, facts):
    assert unknown_mentions(answer, facts, {"ecom.orders", "stg.orders"})


@pytest.mark.parametrize("answer", ["orders_backup", "Orders_Backup", "soft_delete", "deprecation_window"])
def test_guard_no_longer_flags_bare_snake_case_words(answer, facts):
    """Chủ đích: chỉ chặn token DẠNG schema.table (có dấu chấm) — bare
    snake_case (vd từ vựng kỹ thuật chung trong câu trả lời tư vấn) không còn
    bị coi là "có thể bịa tên bảng" nữa. Đánh đổi đã cân nhắc: bỏ lọt tên
    bảng bịa không có dấu chấm, đổi lấy việc không chặn nhầm tư vấn hợp lệ."""
    assert unknown_mentions(answer, facts, {"ecom.orders", "stg.orders"}) == []


def test_guard_uses_case_insensitive_tokens_without_lookbehind():
    assert TABLE_TOKEN.flags & __import__("re").IGNORECASE
    assert "(?<" not in TABLE_TOKEN.pattern


def test_guard_accepts_qualified_name_when_table_and_column_are_known(facts):
    assert unknown_mentions("stg_invoices.amount_paid", facts, {"stg_invoices", "amount_paid"}) == []


def test_guard_accepts_identifier_from_transform_expression(facts):
    facts["confirmed"].append({"transform_expression": "SUM(invoices.amount_paid) AS total_revenue"})

    assert unknown_mentions("SUM(invoices.amount_paid)", facts, {"amount_paid", "total_revenue"}) == []


def test_guard_does_not_trust_identifiers_only_present_in_llm_reasoning(facts):
    facts["confirmed"].append(
        {
            "transform_expression": "SUM(invoices.amount_paid) AS total_revenue",
            "reasoning": "ghost.table_xyz is an internal source.",
        }
    )

    assert unknown_mentions("ghost.table_xyz is involved", facts, {"amount_paid", "total_revenue"}) == [
        "ghost.table_xyz"
    ]


def test_guard_does_not_trust_identifiers_from_lookup_args(facts):
    facts["lookups"] = [{"tool": "traverse", "args": {"table": "ghost.table_xyz", "direction": "upstream"}}]

    assert unknown_mentions("ghost.table_xyz is involved", facts, set()) == ["ghost.table_xyz"]


def test_guard_accepts_identifiers_from_definition_sql(facts):
    facts["confirmed"].append({"definition_sql": "SELECT * FROM raw.invoices WHERE amount_paid > 0"})

    assert unknown_mentions("raw.invoices provides amount_paid", facts, set()) == []
