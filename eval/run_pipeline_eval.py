"""Evaluate the full agent pipeline (static parser + LLM fallback) against
tests/ground_truth/sql — this is the number that maps directly to PRD.md's
SMART goal ("Trích lineage đúng ở mức table, Precision/Recall ≥ 80% cả
hai"), vì đó là kết quả THẬT của agent (parse_node -> llm_extract_node),
không phải 1 component tách riêng.

run_extraction_eval.py đã đo LLM extraction cô lập trên tests/ground_truth/llm
(dùng để tune prompt/threshold); test_parser_service.py đã gate "cạnh mong đợi
có được tìm thấy" cho các case thuần parser. Script này lấp khoảng trống còn
lại: đo Precision/Recall/F1 thật cho TOÀN BỘ agent trên bộ ground-truth
tổng hợp (bao gồm cả case 07_dynamic_sql_fail.sql cố tình cần LLM fallback).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from eval.metrics import (
    ScoreResult,
    TransformTypeAccuracy,
    aggregate,
    column_score,
    score,
    sweep,
    transform_type_accuracy,
)
from src.config import get_settings
from src.models.schemas import LineageEdge
from src.services.llm_extraction_service import PROMPT_VERSION, ExtractionResponse, extract_raw, to_lineage_edges
from src.services.parser_service import SQLParserService


def _load_expected(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("expected JSON must be a flat list of edges (xem tests/ground_truth/expected/*.json)")
    for edge in payload:
        if not isinstance(edge, dict) or "source_table" not in edge or "target_table" not in edge:
            raise ValueError("every expected edge needs source_table and target_table")
    return payload


def _cache_path(cache_dir: Path, sql_text: str, file_name: str, dialect: str, model_name: str) -> Path:
    material = "\0".join([sql_text, file_name, dialect, PROMPT_VERSION, model_name])
    key = hashlib.sha256(material.encode()).hexdigest()
    return cache_dir / f"{key}.json"


def _llm_fallback(
    sql_text: str, name: str, dialect: str, model_name: str, cache_dir: Path, live: bool, refresh: bool
) -> tuple[list[LineageEdge], str]:
    """Trả (edges, nguồn) — nguồn là "cache", "live", hoặc "missing" (cần --live)."""
    path = _cache_path(cache_dir, sql_text, name, dialect, model_name)
    if not refresh and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = ExtractionResponse.model_validate(payload["response"])
        return to_lineage_edges(response, name), "cache"
    if not live:
        return [], "missing"
    response = extract_raw(sql_text, file_name=name, dialect=dialect)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fixture": name,
                "model": model_name,
                "dialect": dialect,
                "prompt_version": PROMPT_VERSION,
                "generated_at": datetime.now(UTC).isoformat(),
                "response": response.model_dump(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return to_lineage_edges(response, name), "live"


def _write_report(
    output_path: Path,
    per_file: list[tuple[str, str, ScoreResult, TransformTypeAccuracy]],
    overall: ScoreResult,
    column_overall: ScoreResult,
    threshold_scores: dict[float, ScoreResult],
    model_name: str,
    dialect: str,
    mode: str,
) -> None:
    lines = [
        "# Pipeline Evaluation (Parser + LLM Fallback)",
        "",
        f"- Model (LLM fallback): `{model_name}`",
        f"- SQL dialect: `{dialect}`",
        f"- Mode: `{mode}` (hybrid = parser trước, LLM fallback chỉ khi parser rỗng — đúng luồng agent thật; "
        "parser_only = bỏ hẳn LLM fallback; llm_only = luôn ép qua LLM bất kể parser thành công hay không, "
        "để so sánh 3 cách tiếp cận trên cùng 1 corpus)",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        "- Đo ở mức table (source_table, target_table), khớp mục tiêu PRD.md \"Trích lineage đúng ở mức table\" — "
        "xem thêm section Column-Level Micro-Average bên dưới cho phép đo nghiêm ngặt hơn (mức cột).",
        "- Mỗi fixture chạy parser trước; parser trả rỗng mới rơi xuống LLM fallback, đúng luồng "
        "`parse_node -> llm_extract_node` của agent thật (xem `src/agents/nodes/lineage_nodes.py`) — chỉ áp dụng "
        "khi mode=hybrid.",
        "",
        "## Per Fixture",
        "",
        "| Fixture | Nguồn | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for name, source, result, type_result in per_file:
        type_text = (
            "n/a"
            if type_result.accuracy is None
            else f"{type_result.correct}/{type_result.total} ({type_result.accuracy:.2f})"
        )
        lines.append(
            f"| {name} | {source} | {result.tp} | {result.fp} | {result.fn} | "
            f"{result.precision:.2f} | {result.recall:.2f} | {result.f1:.2f} | {type_text} | "
            f"missing={result.missing}; spurious={result.spurious} |"
        )
    passed = overall.precision >= 0.8 and overall.recall >= 0.8
    lines.extend(
        [
            "",
            "## Corpus Micro-Average",
            "",
            f"Precision: {overall.precision:.2f}; Recall: {overall.recall:.2f}; F1: {overall.f1:.2f}",
            "",
            f"Mục tiêu PRD.md (`docs/PRD.md` mục 3): Precision ≥ 0.80 và Recall ≥ 0.80 cả hai — "
            f"**{'ĐẠT' if passed else 'CHƯA ĐẠT'}**.",
            "",
            "## Column-Level Micro-Average",
            "",
            f"Precision: {column_overall.precision:.2f}; Recall: {column_overall.recall:.2f}; "
            f"F1: {column_overall.f1:.2f}",
            "",
            "So khớp nghiêm ngặt ở mức `(source_table, source_column, target_table, target_column)` — không phải "
            "mục tiêu PRD (chỉ yêu cầu mức table), chỉ mang tính tham khảo mở rộng. **Lưu ý**: fixture nào có toàn "
            "`source_column`/`target_column` = null ở cả 2 phía sẽ so khớp bằng key rỗng — không phải bằng chứng "
            "thật về độ chính xác cấp cột, chỉ fixture nào thật sự khai báo cột (vd "
            "`13_saas_analytics_pipeline.json`) mới có ý nghĩa đo lường ở đây.",
            "",
            "## Confidence Threshold Sweep",
            "",
            "Quét ngưỡng `confidence_threshold` (src/config.py) trên đúng tập cạnh dự đoán của mode hiện tại — trả "
            "lời câu hỏi PRD.md mục 11 (rủi ro): \"ngưỡng 0.8 chưa có cơ sở thực nghiệm\".",
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
    parser = argparse.ArgumentParser(description="Evaluate the full agent pipeline (parser + LLM fallback).")
    parser.add_argument("--fixtures", default="tests/ground_truth")
    parser.add_argument("--out", default="eval/results/pipeline_eval.md")
    parser.add_argument("--cache-dir", default="eval/.cache")
    parser.add_argument("--live", action="store_true", help="Permit LLM API calls for cache misses.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache entries; requires --live.")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "parser_only", "llm_only"],
        default="hybrid",
        help="hybrid (mặc định, hành vi agent thật) | parser_only (bỏ LLM fallback) | "
        "llm_only (luôn ép qua LLM fallback) — để so sánh 3 cách tiếp cận.",
    )
    parser.add_argument(
        "--thresholds",
        default="0.5,0.6,0.7,0.8,0.9",
        help="Danh sách ngưỡng confidence, phân tách bởi dấu phẩy, để quét precision/recall.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arg_parser = build_parser()
    args = arg_parser.parse_args(argv)
    if args.refresh and not args.live:
        arg_parser.error("--refresh requires --live")

    fixtures = Path(args.fixtures)
    sql_dir = fixtures / "sql"
    expected_dir = fixtures / "expected"
    cache_dir = Path(args.cache_dir)
    settings = get_settings()
    parser_service = SQLParserService(default_dialect=settings.sql_dialect)

    per_file: list[tuple[str, str, ScoreResult, TransformTypeAccuracy]] = []
    missing_llm: list[str] = []
    predicted_by_file: dict[str, list[LineageEdge]] = {}
    expected_by_file: dict[str, list[dict[str, Any]]] = {}
    column_results: list[ScoreResult] = []

    for sql_path in sorted(sql_dir.glob("*.sql")):
        name = sql_path.stem
        expected_path = expected_dir / f"{name}.json"
        if not expected_path.exists():
            print(f"Missing expected fixture: {expected_path}", file=sys.stderr)
            return 1
        try:
            expected = _load_expected(expected_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Malformed expected fixture {expected_path}: {exc}", file=sys.stderr)
            return 1

        parsed_edges, _reason = parser_service.parse_file_with_diagnostics(str(sql_path))
        use_parser = args.mode != "llm_only" and parsed_edges
        if use_parser:
            predicted, source = parsed_edges, "parser"
        elif args.mode == "parser_only":
            predicted, source = [], "parser_only_empty"
        else:
            sql_text = sql_path.read_text(encoding="utf-8")
            try:
                predicted, source = _llm_fallback(
                    sql_text, name, settings.sql_dialect, settings.model_name, cache_dir, args.live, args.refresh
                )
            except ValidationError as exc:
                print(f"Invalid cache entry for {name}: {exc}", file=sys.stderr)
                return 1
            if source == "missing":
                missing_llm.append(name)

        result = score(predicted, expected)
        type_result = transform_type_accuracy(predicted, expected)
        per_file.append((name, source, result, type_result))
        column_results.append(column_score(predicted, expected))
        predicted_by_file[name] = predicted
        expected_by_file[name] = expected

    if missing_llm and not args.live:
        print(f"Cache miss for LLM fallback fixtures: {', '.join(missing_llm)}. Re-run with --live.", file=sys.stderr)
        return 1

    overall = aggregate([result for _, _, result, _ in per_file])
    column_overall = aggregate(column_results)
    thresholds = [float(value.strip()) for value in args.thresholds.split(",")]
    threshold_scores = sweep(predicted_by_file, expected_by_file, thresholds)
    _write_report(
        Path(args.out), per_file, overall, column_overall, threshold_scores, settings.model_name, settings.sql_dialect, args.mode
    )
    print(f"Precision={overall.precision:.3f} Recall={overall.recall:.3f} F1={overall.f1:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
