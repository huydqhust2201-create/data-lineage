"""Run the live chat evaluator against a selected lineage database."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from httpx import HTTPError
from openai import APIError

from eval.chat_score import score_runs
from src.agents.chat import session
from src.config import get_settings
from src.services import chat_service, graph_service

_PROVIDER_ERRORS = (APIError, HTTPError)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate live chat tool selection.")
    parser.add_argument("--database-id", type=int, required=True)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixtures", default="tests/ground_truth/chat/cases")
    return parser


def _load_cases(fixtures: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    required = {"question", "must_call", "must_not_call", "max_calls", "band", "requires_tables", "description_expected"}
    for path in sorted(fixtures.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or required - payload.keys():
            raise ValueError(f"Malformed chat case: {path}")
        optional_lists = [key for key in ("must_contain", "must_not_contain") if key in payload]
        if not all(
            isinstance(payload[key], list)
            for key in ("must_call", "must_not_call", "requires_tables", *optional_lists)
        ):
            raise ValueError(f"Malformed list field in chat case: {path}")
        if (
            not isinstance(payload["question"], str)
            or not isinstance(payload["max_calls"], int)
            or not isinstance(payload["description_expected"], bool)
        ):
            raise ValueError(f"Malformed scalar field in chat case: {path}")
        cases.append({"name": path.stem, **payload})
    if not cases:
        raise ValueError(f"No chat cases found in {fixtures}")
    return cases


def _git_revision() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _phrase_check(answer: str, case: dict[str, Any]) -> dict[str, list[str]]:
    """Check answer content here so full answers never reach the saved report."""
    folded = answer.casefold()
    return {
        "missing_phrases": [p for p in case.get("must_contain", []) if str(p).casefold() not in folded],
        "forbidden_phrases": [p for p in case.get("must_not_contain", []) if str(p).casefold() in folded],
    }


def _trace(case: dict[str, Any], database_id: int, user_id: int) -> dict[str, Any]:
    question = case["question"]
    session.reset(database_id, user_id)
    try:
        response = chat_service.answer_question(question, user_id, database_id)
    except _PROVIDER_ERRORS as exc:
        return {
            "tools_called": [],
            "tool_calls_used": 0,
            "stop_reason": None,
            "answer_rejected": False,
            "api_error": str(exc),
            "missing_phrases": [],
            "forbidden_phrases": [],
            "answer_chars": None,
        }
    return {
        "tools_called": [
            step.tool for step in response.steps if step.error not in {"not_executed", "unknown_tool", "invalid_args"}
        ],
        "tool_calls_used": response.tool_calls_used,
        "stop_reason": response.stop_reason,
        "answer_rejected": any(warning.startswith("answer_rejected_unknown_tables:") for warning in response.warnings),
        "api_error": False,
        **_phrase_check(response.answer, case),
        "answer_chars": len(response.answer),
    }


def run(database_id: int, user_id: int, runs: int, fixtures: Path) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("--runs must be at least 1")
    cases = _load_cases(fixtures)
    available_tables = {str(name).lower() for name in graph_service.snapshot(database_id).nodes}
    traces_by_case: dict[str, list[dict[str, Any]] | None] = {}
    for case in cases:
        if not {table.lower() for table in case["requires_tables"]}.issubset(available_tables):
            traces_by_case[case["name"]] = None
            continue
        traces_by_case[case["name"]] = [_trace(case, database_id, user_id) for _ in range(runs)]

    settings = get_settings()
    report = score_runs(cases, traces_by_case)
    report["meta"] = {
        "model": settings.model_name,
        "git_revision": _git_revision(),
        "database_id": database_id,
        "user_id": user_id,
        "runs_per_case": runs,
        "timestamp": datetime.now(UTC).isoformat(),
        "chat_max_tool_calls": settings.chat_max_tool_calls,
        "chat_max_agent_steps": settings.chat_max_agent_steps,
        "chat_verify_mode": getattr(settings, "chat_verify_mode", "replace"),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args.database_id, args.user_id, args.runs, Path(args.fixtures))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
