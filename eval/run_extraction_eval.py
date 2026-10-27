"""Evaluate cached or explicitly live LLM lineage extraction fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from eval.metrics import aggregate, score, sweep, transform_type_accuracy
from src.config import get_settings
from src.services.llm_extraction_service import PROMPT_VERSION, ExtractionResponse, extract_raw, to_lineage_edges


def _cache_path(cache_dir: Path, sql_text: str, file_name: str, dialect: str, model_name: str) -> Path:
    material = "\0".join([sql_text, file_name, dialect, PROMPT_VERSION, model_name])
    key = hashlib.sha256(material.encode()).hexdigest()
    return cache_dir / f"{key}.json"


def _load_expected(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("expected_edges"), list):
        raise ValueError("expected JSON must contain an expected_edges list")
    edges = payload["expected_edges"]
    for edge in edges:
        if not isinstance(edge, dict) or "source_table" not in edge or "target_table" not in edge:
            raise ValueError("every expected edge needs source_table and target_table")
    return edges


def _write_report(
    output_path: Path,
    per_file: list[tuple[str, Any, Any]],
    overall: Any,
    threshold_scores: dict[float, Any],
    model_name: str,
    dialect: str,
    source_by_file: dict[str, str],
    no_hallucination_fixtures: set[str],
) -> None:
    cache_hits = sum(source == "cache" for source in source_by_file.values())
    live_calls = sum(source == "live" for source in source_by_file.values())
    refusal_total = len(no_hallucination_fixtures)
    refusal_correct = sum(result.fp == 0 for name, result, _ in per_file if name in no_hallucination_fixtures)
    lines = [
        "# LLM Extraction Evaluation",
        "",
        f"- Model: `{model_name}`",
        f"- Prompt version: `{PROMPT_VERSION}`",
        f"- SQL dialect: `{dialect}`",
        f"- Fixture sources: `{cache_hits} cache hits, {live_calls} live queries`",
        "- No-hallucination fixtures are reported separately because empty expected sets do not affect micro-averages.",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Per Fixture",
        "",
        "| Fixture | Source | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for name, result, type_result in per_file:
        type_text = (
            "n/a"
            if type_result.accuracy is None
            else f"{type_result.correct}/{type_result.total} ({type_result.accuracy:.2f})"
        )
        lines.append(
            f"| {name} | {source_by_file[name]} | {result.tp} | {result.fp} | {result.fn} | "
            f"{result.precision:.2f} | {result.recall:.2f} | {result.f1:.2f} | {type_text} | "
            f"missing={result.missing}; spurious={result.spurious} |"
        )
    lines.extend(
        [
            "",
            "## Corpus Micro-Average",
            "",
            f"Precision: {overall.precision:.2f}; Recall: {overall.recall:.2f}; F1: {overall.f1:.2f}",
            f"No-hallucination fixtures: {refusal_correct}/{refusal_total} correct (no hallucinated edges).",
            "",
            "## Confidence Threshold Sweep",
            "",
            "| Threshold | Precision | Recall | F1 |",
            "| ---: | ---: | ---: | ---: |",
        ]
    )
    for threshold, result in threshold_scores.items():
        lines.append(f"| {threshold:.2f} | {result.precision:.2f} | {result.recall:.2f} | {result.f1:.2f} |")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate LLM extraction fixtures from cache or with explicit live calls."
    )
    parser.add_argument("--fixtures", default="tests/ground_truth/llm")
    parser.add_argument("--out", default="eval/results/llm_extraction_eval.md")
    parser.add_argument("--cache-dir", default="eval/.cache")
    parser.add_argument("--live", action="store_true", help="Permit API calls for cache misses.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache entries; requires --live.")
    parser.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.9")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.refresh and not args.live:
        parser.error("--refresh requires --live")

    fixtures = Path(args.fixtures)
    sql_dir = fixtures / "sql"
    expected_dir = fixtures / "expected"
    cache_dir = Path(args.cache_dir)
    settings = get_settings()
    expected_by_file: dict[str, list[dict[str, Any]]] = {}
    sql_by_file: dict[str, str] = {}
    for sql_path in sorted(sql_dir.glob("*.sql")):
        name = sql_path.stem
        expected_path = expected_dir / f"{name}.json"
        if not expected_path.exists():
            print(f"Missing expected fixture: {expected_path}", file=sys.stderr)
            return 1
        try:
            expected_by_file[name] = _load_expected(expected_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Malformed expected fixture {expected_path}: {exc}", file=sys.stderr)
            return 1
        sql_by_file[name] = sql_path.read_text(encoding="utf-8")

    responses: dict[str, ExtractionResponse] = {}
    source_by_file: dict[str, str] = {}
    missing: list[str] = []
    for name, sql_text in sql_by_file.items():
        path = _cache_path(cache_dir, sql_text, name, settings.sql_dialect, settings.model_name)
        if not args.refresh and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                responses[name] = ExtractionResponse.model_validate(payload["response"])
                source_by_file[name] = "cache"
            except (KeyError, OSError, ValidationError, json.JSONDecodeError) as exc:
                print(f"Invalid cache entry {path}: {exc}", file=sys.stderr)
                return 1
        else:
            missing.append(name)

    if missing and not args.live:
        print(f"Cache miss for fixtures: {', '.join(missing)}. Re-run with --live.", file=sys.stderr)
        return 1

    for name in missing:
        sql_text = sql_by_file[name]
        response = extract_raw(sql_text, file_name=name, dialect=settings.sql_dialect)
        responses[name] = response
        source_by_file[name] = "live"
        path = _cache_path(cache_dir, sql_text, name, settings.sql_dialect, settings.model_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "fixture": name,
                    "model": settings.model_name,
                    "dialect": settings.sql_dialect,
                    "prompt_version": PROMPT_VERSION,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "response": response.model_dump(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    predicted_by_file = {name: to_lineage_edges(response, name) for name, response in responses.items()}
    per_file = [
        (name, score(predicted_by_file[name], expected), transform_type_accuracy(predicted_by_file[name], expected))
        for name, expected in expected_by_file.items()
    ]
    overall = aggregate([result for _, result, _ in per_file])
    try:
        thresholds = [float(value.strip()) for value in args.thresholds.split(",")]
    except ValueError:
        parser.error("--thresholds must be comma-separated numbers")
    _write_report(
        Path(args.out),
        per_file,
        overall,
        sweep(predicted_by_file, expected_by_file, thresholds),
        settings.model_name,
        settings.sql_dialect,
        source_by_file,
        {name for name, expected in expected_by_file.items() if not expected},
    )
    print(f"Precision={overall.precision:.3f} Recall={overall.recall:.3f} F1={overall.f1:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
