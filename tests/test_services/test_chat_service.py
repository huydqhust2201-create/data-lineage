from src.agents.chat.resolve import question_with_choice
from src.agents.chat.session import Turn
from src.services.chat_service import _history_text


def test_history_text_includes_question_and_answer_preview():
    """Trước đây _history_text chỉ đưa question + resolved_table vào history,
    KHÔNG có answer — câu hỏi meta hỏi về kết luận của lượt trước (không chỉ
    hỏi cái gì) không có gì để trả lời dựa vào."""
    turns = [Turn(question="impact orders", resolved_table="raw.orders", answer="raw.orders affects stg.orders")]
    text = _history_text(turns)
    assert "impact orders" in text
    assert "raw.orders affects stg.orders" in text


def test_history_text_truncates_long_answers():
    long_answer = "x" * 500
    turns = [Turn(question="q", resolved_table=None, answer=long_answer)]
    text = _history_text(turns)
    assert len(text) < len(long_answer) + 100
    assert text.endswith('..."')


def test_history_text_handles_multiple_turns_in_order():
    turns = [
        Turn(question="q1", resolved_table="a", answer="ans1"),
        Turn(question="q2", resolved_table="b", answer="ans2"),
    ]
    text = _history_text(turns)
    assert text.index("q1") < text.index("q2")


def test_question_with_choice_replaces_only_a_complete_identifier():
    assert question_with_choice("revenue_alert có gì?", "revenue_alert", "revenue_alerts_staging") == "revenue_alerts_staging có gì?"
    assert (
        question_with_choice(
            "so sánh revenue_alert và `revenue_alerts_staging`", "revenue_alert", "revenue_alerts_final"
        )
        == "so sánh revenue_alerts_final và `revenue_alerts_staging`"
    )
    assert question_with_choice("REVENUE_ALERT có gì?", "revenue_alert", "revenue_alerts_staging") == "revenue_alerts_staging có gì?"
    assert question_with_choice("không có tên đó", "revenue_alert", "revenue_alerts_staging") == "không có tên đó"
