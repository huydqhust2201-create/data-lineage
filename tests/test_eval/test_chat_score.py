import json
import subprocess
from types import SimpleNamespace

import httpx
import networkx as nx
import openai
import pytest

from eval import run_chat_eval as runner
from eval.chat_score import score_runs


def case(name="lineage", **overrides):
    return {
        "name": name,
        "question": "where from?",
        "must_call": ["traverse"],
        "must_not_call": ["breaking_changes"],
        "max_calls": 3,
        "band": "expect-single-tool",
        "description_expected": False,
        "requires_tables": ["department_revenue"],
    } | overrides


def trace(**overrides):
    return {
        "tools_called": ["traverse"],
        "tool_calls_used": 1,
        "stop_reason": "completed",
        "api_error": False,
    } | overrides


def test_score_runs_uses_tool_sets_and_micro_average():
    report = score_runs(
        [case(), case("blocked")],
        {"lineage": [trace()], "blocked": [trace(tools_called=["breaking_changes"])]},
    )

    assert report["cases"][0]["status"] == "passed"
    assert report["cases"][1]["runs"][0]["failures"] == ["missing_tools: traverse", "forbidden_tools: breaking_changes"]
    assert report["summary"]["micro_average"] == 0.5


def test_score_runs_separates_tool_and_content_failures():
    content_case = case(must_contain=["department_revenue"])
    report = score_runs(
        [content_case, case("tool-failure")],
        {
            "lineage": [trace(missing_phrases=["department_revenue"])],
            "tool-failure": [trace(tools_called=[])],
        },
    )

    content_run, tool_run = (item["runs"][0] for item in report["cases"])
    assert (content_run["tool_passed"], content_run["content_passed"], content_run["passed"]) == (True, False, False)
    assert (tool_run["tool_passed"], tool_run["content_passed"], tool_run["passed"]) == (False, True, False)
    assert report["summary"]["tool_micro_average"] == 0.5
    assert report["summary"]["content_micro_average"] == 0.5
    assert report["summary"]["micro_average"] == 0.0


def test_score_runs_api_error_fails_both_metric_dimensions():
    run = score_runs([case()], {"lineage": [trace(api_error="timeout")]})["cases"][0]["runs"][0]

    assert (run["tool_passed"], run["content_passed"], run["passed"]) == (False, False, False)
    assert run["failures"] == ["api_error"]


def test_score_runs_no_content_contract_passes_content_dimension():
    report = score_runs([case()], {"lineage": [trace()]})

    assert report["cases"][0]["runs"][0]["content_passed"] is True
    assert report["summary"]["content_micro_average"] == 1.0


def test_score_runs_preserves_combined_micro_average():
    report = score_runs(
        [case(), case("missing")],
        {"lineage": [trace()], "missing": [trace(tools_called=[])]},
    )

    assert report["summary"]["micro_average"] == 0.5


def test_score_runs_reports_median_answer_length_for_passing_non_api_runs():
    report = score_runs(
        [case()],
        {"lineage": [trace(answer_chars=100), trace(answer_chars=500), trace(answer_chars=900, tools_called=[]), trace(api_error="timeout")]},
    )

    assert report["summary"]["median_answer_chars_passing_runs"] == 300


def test_score_runs_uses_none_when_no_answer_length_is_available():
    report = score_runs([case()], {"lineage": [trace(answer_chars=None, tools_called=[])]})

    assert report["summary"]["median_answer_chars_passing_runs"] is None


def test_score_runs_skips_missing_graph_requirements_and_excludes_api_errors_from_average():
    report = score_runs(
        [case(), case("missing")],
        {"lineage": [trace(tool_calls_used=2), trace(api_error="timeout", tools_called=[], tool_calls_used=0)], "missing": None},
    )

    assert report["cases"][1]["status"] == "skipped"
    assert report["summary"]["micro_average"] == 0.5
    assert report["summary"]["average_tool_calls_per_executed_run"] == 2.0


def test_score_runs_uses_tool_calls_used_not_nonexecuted_steps():
    report = score_runs(
        [case()],
        {"lineage": [trace(tools_called=["traverse", "breaking_changes"], tool_calls_used=1, stop_reason="budget_exhausted")]},
    )

    assert report["summary"]["budget_exhausted_runs"] == 1
    assert report["summary"]["average_tool_calls_per_executed_run"] == 1.0


def test_score_runs_reports_description_misuse_only_for_cases_where_it_is_not_expected():
    report = score_runs(
        [case(), case("description", description_expected=True)],
        {
            "lineage": [trace(tools_called=["search_column_description"]), trace()],
            "description": [trace(tools_called=["search_column_description"])],
        },
    )

    assert report["summary"]["description_misuse_rate"] == 0.5


def test_score_runs_reports_rejected_answers_without_changing_tool_pass_rate():
    report = score_runs([case()], {"lineage": [trace(answer_rejected=True)]})

    assert report["cases"][0]["pass_rate"] == 1.0
    assert report["cases"][0]["runs"][0]["answer_rejected"] is True
    assert report["summary"]["answer_rejected_runs"] == 1


def test_score_runs_does_not_count_unverified_answers_as_rejected():
    report = score_runs([case()], {"lineage": [trace(answer_rejected=False)]})

    assert report["cases"][0]["runs"][0]["answer_rejected"] is False
    assert report["summary"]["answer_rejected_runs"] == 0


def test_runner_does_not_mark_unverified_warning_as_answer_rejection(monkeypatch):
    monkeypatch.setattr(runner.session, "reset", lambda *_args: None)
    monkeypatch.setattr(
        runner.chat_service,
        "answer_question",
        lambda *_a, **_k: SimpleNamespace(
            steps=[],
            tool_calls_used=0,
            stop_reason="completed",
            warnings=["answer_unverified_unknown_tables: raw.customers"],
            answer="raw.customers feeds the report.",
        ),
    )

    result = runner._trace({"question": "why?"}, 1, 12)

    assert result["answer_rejected"] is False


def test_runner_skips_case_when_its_required_table_is_absent(monkeypatch, tmp_path):
    fixture = tmp_path / "case.json"
    fixture.write_text(json.dumps({key: value for key, value in case().items() if key != "name"}), encoding="utf-8")
    monkeypatch.setattr(runner.graph_service, "snapshot", lambda _database_id: nx.MultiDiGraph([("department_revenue", "other")]))
    monkeypatch.setattr(runner, "_trace", lambda *_args: trace())

    report = runner.run(1, 12, 2, tmp_path)

    assert report["cases"][0]["status"] == "passed"


def test_runner_marks_case_skipped_when_required_table_is_not_in_graph(monkeypatch, tmp_path):
    fixture = tmp_path / "case.json"
    fixture.write_text(json.dumps({key: value for key, value in case().items() if key != "name"}), encoding="utf-8")
    monkeypatch.setattr(runner.graph_service, "snapshot", lambda _database_id: nx.MultiDiGraph())

    report = runner.run(1, 12, 2, tmp_path)

    assert report["cases"][0]["status"] == "skipped"
    assert report["summary"]["micro_average"] == 0.0


def test_eval_chat_make_target_requires_database_id():
    result = subprocess.run(["make", "eval-chat"], capture_output=True, text=True, check=False)

    assert result.returncode != 0
    assert "DATABASE_ID is required" in result.stdout


def test_eval_chat_make_target_requires_user_id():
    result = subprocess.run(["make", "eval-chat", "DATABASE_ID=1"], capture_output=True, text=True, check=False)

    assert result.returncode != 0
    assert "USER_ID is required" in result.stdout


def test_trace_resets_session_before_each_independent_run(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.session, "reset", lambda database_id, user_id: calls.append(("reset", database_id, user_id)))
    monkeypatch.setattr(
        runner.chat_service,
        "answer_question",
        lambda *args: calls.append(("answer", *args)) or SimpleNamespace(
            steps=[], tool_calls_used=0, stop_reason="completed", warnings=[], answer="ok"
        ),
    )

    runner._trace({"question": "first?"}, 7, 13)
    runner._trace({"question": "second?"}, 7, 13)

    assert calls == [
        ("reset", 7, 13),
        ("answer", "first?", 13, 7),
        ("reset", 7, 13),
        ("answer", "second?", 13, 7),
    ]


@pytest.mark.parametrize(
    "error",
    [
        lambda: openai.APIStatusError(
            "bad gateway", response=httpx.Response(502, request=httpx.Request("POST", "https://example.test")), body=None
        ),
        lambda: openai.APIConnectionError(request=httpx.Request("POST", "https://example.test")),
        lambda: httpx.HTTPError("transport failure"),
    ],
)
def test_trace_turns_provider_errors_into_api_error(monkeypatch, error):
    monkeypatch.setattr(runner.session, "reset", lambda *_args: None)
    monkeypatch.setattr(runner.chat_service, "answer_question", lambda *_args: (_ for _ in ()).throw(error()))

    result = runner._trace({"question": "why?"}, 1, 12)

    assert result["api_error"]


@pytest.mark.parametrize("error", [TypeError("wrong signature"), AttributeError("missing attribute")])
def test_trace_does_not_hide_programming_errors(monkeypatch, error):
    monkeypatch.setattr(runner.session, "reset", lambda *_args: None)
    monkeypatch.setattr(runner.chat_service, "answer_question", lambda *_args: (_ for _ in ()).throw(error))

    with pytest.raises(type(error)):
        runner._trace({"question": "why?"}, 1, 12)


def test_trace_reports_missing_and_forbidden_content(monkeypatch):
    monkeypatch.setattr(runner.session, "reset", lambda *_args: None)
    monkeypatch.setattr(
        runner.chat_service,
        "answer_question",
        lambda *_a, **_k: SimpleNamespace(
            steps=[], tool_calls_used=1, stop_reason="completed", warnings=[],
            answer="Mình chưa biết bạn đang nói đến bảng nào.",
        ),
    )
    case = {
        "question": "revenue_alerts_staging bị lỗi, tại sao?",
        "must_call": [], "must_not_call": [], "max_calls": 4,
        "must_contain": ["department_revenue"],
        "must_not_contain": ["chưa biết bạn đang nói đến bảng nào"],
    }

    trace = runner._trace(case, 1, 12)
    run = score_runs([{"name": "c", **case}], {"c": [trace]})["cases"][0]["runs"][0]

    assert trace["missing_phrases"] == ["department_revenue"]
    assert trace["forbidden_phrases"] == ["chưa biết bạn đang nói đến bảng nào"]
    assert run["passed"] is False
    assert any(f.startswith("missing_content:") for f in run["failures"])
    assert any(f.startswith("forbidden_content:") for f in run["failures"])


def test_content_checks_are_optional_and_case_insensitive(monkeypatch):
    monkeypatch.setattr(runner.session, "reset", lambda *_args: None)
    monkeypatch.setattr(
        runner.chat_service,
        "answer_question",
        lambda *_a, **_k: SimpleNamespace(
            steps=[], tool_calls_used=1, stop_reason="completed", warnings=[],
            answer="Ngưỡng là APPOINTMENT_COUNT < 5.",
        ),
    )

    without = runner._trace({"question": "q"}, 1, 12)
    assert without["missing_phrases"] == [] and without["forbidden_phrases"] == []

    with_check = runner._trace({"question": "q", "must_contain": ["appointment_count < 5"]}, 1, 12)
    assert with_check["missing_phrases"] == []
