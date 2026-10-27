"""Pure scoring for repeatable chat-tool evaluation runs."""

from __future__ import annotations

from statistics import median
from typing import Any


def _score_run(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    tools_called = trace.get("tools_called", [])
    tool_failures: list[str] = []
    content_failures: list[str] = []
    if trace.get("api_error"):
        tool_failures.append("api_error")
        content_failures.append("api_error")
    else:
        missing = sorted(set(case["must_call"]) - set(tools_called))
        forbidden = sorted(set(case["must_not_call"]) & set(tools_called))
        if missing:
            tool_failures.append("missing_tools: " + ", ".join(missing))
        if forbidden:
            tool_failures.append("forbidden_tools: " + ", ".join(forbidden))
        if trace.get("tool_calls_used", 0) > case["max_calls"]:
            tool_failures.append(f"max_calls_exceeded: {trace['tool_calls_used']} > {case['max_calls']}")
        if trace.get("missing_phrases"):
            content_failures.append("missing_content: " + ", ".join(trace["missing_phrases"]))
        if trace.get("forbidden_phrases"):
            content_failures.append("forbidden_content: " + ", ".join(trace["forbidden_phrases"]))
    failures = tool_failures + [failure for failure in content_failures if failure not in tool_failures]
    return {
        "tools_called": tools_called,
        "tool_calls_used": trace.get("tool_calls_used", 0),
        "stop_reason": trace.get("stop_reason"),
        "answer_rejected": bool(trace.get("answer_rejected")),
        "tool_passed": not tool_failures,
        "content_passed": not content_failures,
        "passed": not failures,
        "failures": failures,
        "api_error": bool(trace.get("api_error")),
        "answer_chars": None if trace.get("api_error") else trace.get("answer_chars"),
    }


def score_runs(cases: list[dict[str, Any]], traces_by_case: dict[str, list[dict[str, Any]] | None]) -> dict[str, Any]:
    """Score offline tool traces against declarative case expectations.

    A ``None`` trace list denotes a skipped case whose graph prerequisites were
    absent. API errors are failures in the pass-rate denominator but are kept
    out of the tool-call average because their partial trace is not a complete
    agent run.
    """
    report_cases: list[dict[str, Any]] = []
    executed_runs: list[dict[str, Any]] = []
    description_not_expected_runs: list[dict[str, Any]] = []
    for case in cases:
        traces = traces_by_case.get(case["name"])
        if traces is None:
            report_cases.append({"name": case["name"], "runs": [], "pass_rate": 0.0, "status": "skipped"})
            continue
        runs = [_score_run(case, trace) for trace in traces]
        executed_runs.extend(runs)
        if case.get("description_expected") is False:
            description_not_expected_runs.extend(runs)
        passed = sum(run["passed"] for run in runs)
        report_cases.append(
            {
                "name": case["name"],
                "runs": runs,
                "pass_rate": passed / len(runs) if runs else 0.0,
                "status": "passed" if runs and passed == len(runs) else "failed",
            }
        )

    non_api_runs = [run for run in executed_runs if not run["api_error"]]
    passing_lengths = [run["answer_chars"] for run in executed_runs if run["passed"] and run["answer_chars"] is not None]
    return {
        "cases": report_cases,
        "summary": {
            "micro_average": sum(run["passed"] for run in executed_runs) / len(executed_runs)
            if executed_runs
            else 0.0,
            "tool_micro_average": sum(run["tool_passed"] for run in executed_runs) / len(executed_runs)
            if executed_runs
            else 0.0,
            "content_micro_average": sum(run["content_passed"] for run in executed_runs) / len(executed_runs)
            if executed_runs
            else 0.0,
            "budget_exhausted_runs": sum(run["stop_reason"] == "budget_exhausted" for run in executed_runs),
            "answer_rejected_runs": sum(run["answer_rejected"] for run in executed_runs),
            "average_tool_calls_per_executed_run": (
                sum(run["tool_calls_used"] for run in non_api_runs) / len(non_api_runs) if non_api_runs else 0.0
            ),
            "description_misuse_rate": (
                sum("search_column_description" in run["tools_called"] for run in description_not_expected_runs)
                / len(description_not_expected_runs)
                if description_not_expected_runs
                else 0.0
            ),
            "median_answer_chars_passing_runs": median(passing_lengths) if passing_lengths else None,
        },
    }
