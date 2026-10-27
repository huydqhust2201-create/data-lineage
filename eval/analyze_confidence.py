"""Read cached lineage extraction responses and report confidence behavior."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

from eval.metrics import edge_key
from eval.run_extraction_eval import _cache_path
from src.config import get_settings
from src.services.llm_extraction_service import PROMPT_VERSION, ExtractionResponse, to_lineage_edges


def _load_expected(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("expected_edges"), list):
        raise ValueError("expected JSON must contain an expected_edges list")
    return payload["expected_edges"]


def _parse_thresholds(value: str) -> list[float]:
    try:
        return sorted({float(item.strip()) for item in value.split(",")})
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--thresholds must be comma-separated numbers") from exc


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Analyze cached LLM extraction confidences without calling an LLM.")
    parser.add_argument("--fixtures", default="tests/ground_truth/llm")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--model", default=settings.model_name)
    parser.add_argument("--dialect", default=settings.sql_dialect)
    parser.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.9")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    thresholds = _parse_thresholds(args.thresholds)
    fixtures = Path(args.fixtures)
    cache_dir = Path(args.cache_dir)
    expected_dir = fixtures / "expected"
    sql_paths = sorted((fixtures / "sql").glob("*.sql"))

    expected_by_name: dict[str, list[dict[str, Any]]] = {}
    sql_by_name: dict[str, str] = {}
    for sql_path in sql_paths:
        expected_path = expected_dir / f"{sql_path.stem}.json"
        if not expected_path.exists():
            print(f"Missing expected fixture: {expected_path}", file=sys.stderr)
            return 1
        try:
            expected_by_name[sql_path.stem] = _load_expected(expected_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Malformed expected fixture {expected_path}: {exc}", file=sys.stderr)
            return 1
        sql_by_name[sql_path.stem] = sql_path.read_text(encoding="utf-8")

    responses: dict[str, ExtractionResponse] = {}
    missing: list[str] = []
    for name, sql_text in sql_by_name.items():
        path = _cache_path(cache_dir, sql_text, name, args.dialect, args.model)
        if not path.exists():
            missing.append(name)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for field, expected_value in {
                "model": args.model,
                "dialect": args.dialect,
                "prompt_version": PROMPT_VERSION,
            }.items():
                if payload.get(field) != expected_value:
                    print(
                        f"Cache metadata mismatch in {path}: {field}={payload.get(field)!r}, "
                        f"expected {expected_value!r}",
                        file=sys.stderr,
                    )
                    return 1
            responses[name] = ExtractionResponse.model_validate(payload["response"])
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Invalid cache entry {path}: {exc}", file=sys.stderr)
            return 1

    if missing:
        print(f"Cache miss for fixtures: {', '.join(missing)}. Re-run the evaluator with --live.", file=sys.stderr)
        return 1

    rows: list[tuple[float, str, str, str]] = []
    for name, response in responses.items():
        expected_keys = {
            edge_key(str(item["source_table"]), str(item["target_table"])) for item in expected_by_name[name]
        }
        for edge in to_lineage_edges(response, name):
            verdict = "TP" if edge_key(edge.source_table, edge.target_table) in expected_keys else "FP"
            rows.append((edge.confidence, name, verdict, f"{edge.source_table} -> {edge.target_table}"))

    rows.sort(key=lambda row: (row[0], row[1], row[3]))
    print(f"Model: {args.model}")
    print(f"Dialect: {args.dialect}")
    print(f"Prompt version: {PROMPT_VERSION}")
    print(f"Cache directory: {cache_dir}")
    print(f"Accepted cache entries: {len(responses)}")
    print()
    print("| Confidence | Fixture | Verdict | Edge |")
    print("| ---: | --- | --- | --- |")
    for confidence, name, verdict, edge in rows:
        print(f"| {confidence:.2f} | {name} | {verdict} | {edge} |")

    distribution = Counter(confidence for confidence, _, _, _ in rows)
    print()
    print("Confidence distribution:")
    for confidence in sorted(distribution):
        print(f"{confidence:.2f}: {distribution[confidence]}")

    between_06_07 = sum(0.6 <= confidence < 0.7 for confidence, _, _, _ in rows)
    true_between_05_07 = sum(verdict == "TP" and 0.5 <= confidence < 0.7 for confidence, _, verdict, _ in rows)
    print(f"edges in [0.6, 0.7): {between_06_07}")
    print(f"correctly-predicted (TP) edges in [0.5, 0.7): {true_between_05_07}")
    for lower, upper in pairwise(thresholds):
        count = sum(lower <= confidence < upper for confidence, _, _, _ in rows)
        if count == 0:
            print(f"THRESHOLDS {lower:g} AND {upper:g} ARE INDISTINGUISHABLE ON THIS CORPUS (0 edges between them)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
