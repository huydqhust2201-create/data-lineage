"""Benchmark hiệu năng THẬT — không phải test pass/fail, chỉ đo số liệu thật
(latency ingest, latency chat, chi phí LLM, độ trễ theo kích thước đồ thị) để
đưa vào báo cáo/pitch. Cần Postgres + OpenRouter thật đang chạy, không mock.

Không bịa số: phần nào chưa đo được thật (vd usage_stats rỗng vì chưa chạy
extract_raw() lần nào trong tiến trình này) sẽ ghi rõ "chưa đo được" trong
báo cáo thay vì điền placeholder.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx

from eval.run_chat_eval import _load_cases
from src.config import get_settings
from src.services import (
    chat_service,
    database_service,
    graph_service,
    impact_service,
    ingest_service,
    llm_extraction_service,
)
from tests.test_services import test_impact_latency

_GRAPH_SCALING_COMBOS = [(4, 6), (6, 9), (8, 12)]
_INGEST_TARGETS = ["samples/jaffle-shop", "samples/complex_pipeline", "samples/hospital"]
# ingest_service quét *.sql qua Path(input_path).rglob() — chỉ hoạt động với
# THƯ MỤC, không phải 1 file đơn lẻ (đã tự vấp bug này khi test thủ công
# trước đó trong session) — nên trỏ vào samples/complex_pipeline/ (thư mục),
# không phải trực tiếp warehouse_pipeline.sql. Thư mục này có 3 file (1 file
# lớn hợp lệ 703 dòng + 2 file cố ý fail cho LLM fallback) nên số liệu ở đây
# là "ingest 1 thư mục nhiều file thật", không tách riêng được 1 file lớn.
# samples/hospital: domain THẬT mà tests/ground_truth/chat/cases/*.json cần
# (doctors/patients/invoices) — ingest vào CÙNG database scratch để phần Chat
# Turn Latency bên dưới có bảng khớp mà đo, không cần --database-id riêng.


def _git_revision() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


async def _time_ingest(path: str, database_id: int, user_id: int) -> tuple[float, Any]:
    started = time.perf_counter()
    response = await ingest_service.run_ingest(path, database_id, user_id)
    return time.perf_counter() - started, response


def run_ingest_benchmark(owner_id: int) -> tuple[int, list[dict[str, Any]]]:
    """Dùng 1 database SCRATCH riêng (tạo mới, xoá được sau) — không đụng
    database demo thật đang có dữ liệu."""
    scratch = database_service.create_database(owner_id, f"perf-bench-{int(time.time())}")
    assert scratch is not None, "Không tạo được database scratch cho benchmark"
    results = []
    for path in _INGEST_TARGETS:
        elapsed, response = asyncio.run(_time_ingest(path, scratch.id, owner_id))
        results.append(
            {
                "path": path,
                "elapsed_s": round(elapsed, 3),
                "sql_files_found": response.sql_files_found,
                "parsed_count": response.parsed_count,
                "pending_review_count": response.pending_review_count,
            }
        )
    return scratch.id, results


def run_chat_benchmark(database_id: int, user_id: int, fixtures: Path) -> tuple[list[float], list[str]]:
    """Wall-clock mỗi lượt chat trên corpus có sẵn của run_chat_eval.py — KHÔNG
    sửa run_chat_eval.py (tránh ảnh hưởng ~25 snapshot cũ), chỉ tái dùng
    _load_cases() để đọc case, tự đo thời gian bằng time.perf_counter()."""
    cases = _load_cases(fixtures)
    available_tables = {str(name).lower() for name in graph_service.snapshot(database_id).nodes}
    latencies: list[float] = []
    skipped: list[str] = []
    for case in cases:
        if not {table.lower() for table in case["requires_tables"]}.issubset(available_tables):
            skipped.append(case["name"])
            continue
        started = time.perf_counter()
        chat_service.answer_question(case["question"], user_id, database_id)
        latencies.append(time.perf_counter() - started)
    return latencies, skipped


def run_graph_scaling_benchmark() -> list[dict[str, Any]]:
    """Gọi nguyên `_build_wide_deep_graph()` từ test_impact_latency.py (import
    module trực tiếp, không viết lại logic dựng đồ thị) ở vài tổ hợp
    (depth, fanout) ngoài (8,12) đã có sẵn trong pytest, báo cáo thời gian
    thật thay vì chỉ pass/fail. Dùng đúng `_DATABASE_ID` nội bộ của module đó
    (=1) — an toàn tuyệt đối với dữ liệu demo thật vì graph_service._graphs
    chỉ là dict in-memory riêng của TIẾN TRÌNH này (script chạy tách biệt
    hoàn toàn với server thật đang chạy, không chia sẻ RAM)."""
    database_id = test_impact_latency._DATABASE_ID
    results = []
    for depth, fanout in _GRAPH_SCALING_COMBOS:
        graph_service._reset_graph(database_id, nx.MultiDiGraph())
        test_impact_latency._build_wide_deep_graph(depth=depth, fanout=fanout)
        started = time.perf_counter()
        result = impact_service.query_impact(database_id, "root", column="id", direction="downstream")
        elapsed = time.perf_counter() - started
        results.append(
            {
                "depth": depth,
                "fanout": fanout,
                "confirmed_edges_returned": len(result.confirmed),
                "elapsed_s": round(elapsed, 3),
            }
        )
        graph_service._reset_graph(database_id, None)
    return results


_OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS = {
    # Giá OpenRouter cho openai/gpt-4o-mini, tự tra tại openrouter.ai/models
    # lúc viết báo cáo — GIÁ CÓ THỂ ĐÃ ĐỔI, luôn kiểm tra lại trước khi dùng
    # số này cho tài liệu chính thức/pitch.
    "prompt": 0.15,
    "completion": 0.60,
    "as_of": "2026-08-31 (tự tra cứu, cần xác minh lại)",
}


def _write_report(
    output_path: Path,
    ingest_results: list[dict[str, Any]],
    chat_latencies: list[float],
    chat_skipped: list[str],
    graph_results: list[dict[str, Any]],
    usage_stats: dict[str, int],
    model_name: str,
) -> None:
    lines = [
        "# Performance Benchmark (số liệu thật, chạy cục bộ)",
        "",
        f"- Model: `{model_name}`",
        f"- Git revision: `{_git_revision()}`",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        "- Chưa deploy thật (README: \"chưa deploy — kế hoạch W4-W5\") — số liệu dưới đây đo trên máy dev, "
        "KHÔNG phải benchmark production thật, chỉ phục vụ báo cáo/pitch có số liệu thật thay vì ước lượng.",
        "",
        "## 1. Ingest Latency theo kích thước input",
        "",
        "| Input | Elapsed (s) | SQL files | Parsed edges | Pending review |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in ingest_results:
        lines.append(
            f"| `{r['path']}` | {r['elapsed_s']} | {r['sql_files_found']} | {r['parsed_count']} | "
            f"{r['pending_review_count']} |"
        )

    lines.extend(["", "## 2. Chat Turn Latency (p50/p95)", ""])
    if chat_latencies:
        sorted_lat = sorted(chat_latencies)
        p50 = statistics.median(sorted_lat)
        p95_index = min(len(sorted_lat) - 1, int(round(0.95 * (len(sorted_lat) - 1))))
        p95 = sorted_lat[p95_index]
        lines.extend(
            [
                f"- Số case đo được: {len(chat_latencies)} (bỏ qua {len(chat_skipped)} case vì database chưa có "
                f"đủ bảng yêu cầu: {', '.join(chat_skipped) if chat_skipped else '(không có)'})",
                f"- p50: {p50:.2f}s; p95: {p95:.2f}s; min: {min(sorted_lat):.2f}s; max: {max(sorted_lat):.2f}s",
            ]
        )
    else:
        lines.append(
            "- **Chưa đo được**: không case nào trong `tests/ground_truth/chat/cases/` khớp bảng đã ingest ở "
            "database scratch (đã tự ingest `samples/hospital` — xem mục 1). Kiểm tra lại tên bảng "
            "`requires_tables` trong các file case còn khớp với schema `samples/hospital` hiện tại không."
        )

    lines.extend(["", "## 3. Chi phí LLM ước tính (dựa trên token usage thật)", ""])
    if usage_stats["calls"] > 0:
        prompt_cost = usage_stats["prompt_tokens"] / 1_000_000 * _OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS["prompt"]
        completion_cost = (
            usage_stats["completion_tokens"] / 1_000_000 * _OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS["completion"]
        )
        lines.extend(
            [
                f"- Số lần gọi LLM extraction đo được trong lượt chạy này: {usage_stats['calls']}",
                f"- Tổng token: {usage_stats['prompt_tokens']} prompt + {usage_stats['completion_tokens']} "
                f"completion = {usage_stats['total_tokens']} tokens",
                f"- Ước tính chi phí: ${prompt_cost + completion_cost:.5f} (giá OpenRouter "
                f"`openai/gpt-4o-mini`: ${_OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS['prompt']}/1M prompt + "
                f"${_OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS['completion']}/1M completion, tra cứu "
                f"{_OPENROUTER_GPT4O_MINI_PRICE_PER_1M_TOKENS['as_of']} — **kiểm tra lại giá trước khi dùng cho "
                "tài liệu chính thức**)",
            ]
        )
    else:
        lines.append(
            "- **Chưa đo được**: không có lần gọi LLM extraction nào trong tiến trình chạy benchmark này "
            "(nhánh Ingest Latency ở trên không cần LLM fallback, mọi file parse tĩnh thành công). Chạy "
            "`python -c \"from src.services import llm_extraction_service as s; s.extract_raw(open('tests/ground_truth/sql/07_dynamic_sql_fail.sql').read())\"` "
            "trước rồi chạy lại benchmark để có số liệu thật."
        )

    lines.extend(
        [
            "",
            "## 4. Graph-Size Scaling (Impact Query)",
            "",
            "Tái dùng `_build_wide_deep_graph()` từ `tests/test_services/test_impact_latency.py` (đồ thị tổng "
            "hợp, KHÔNG phải dữ liệu demo thật) — mục tiêu PRD: impact query < 3s.",
            "",
            "| Depth | Fanout | Confirmed edges | Elapsed (s) | < 3s (PRD)? |",
            "| ---: | ---: | ---: | ---: | :---: |",
        ]
    )
    for r in graph_results:
        lines.append(
            f"| {r['depth']} | {r['fanout']} | {r['confirmed_edges_returned']} | {r['elapsed_s']} | "
            f"{'✅' if r['elapsed_s'] < 3.0 else '❌'} |"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Đo hiệu năng thật (ingest/chat/LLM cost/graph scaling).")
    parser.add_argument(
        "--user-id", type=int, required=True, help="User dùng làm owner cho database scratch (tự tạo, tự ingest samples/hospital cho phần Chat Latency)."
    )
    parser.add_argument("--chat-fixtures", default="tests/ground_truth/chat/cases")
    parser.add_argument("--out", default="eval/results/performance_benchmark.md")
    parser.add_argument("--skip-chat", action="store_true", help="Bỏ qua phần Chat Latency (đỡ gọi LLM nhiều lần).")
    parser.add_argument("--skip-graph-scaling", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    llm_extraction_service.clear_usage_stats()

    scratch_database_id, ingest_results = run_ingest_benchmark(args.user_id)
    print(f"Ingest benchmark done, dùng database scratch id={scratch_database_id}", file=sys.stderr)

    chat_latencies: list[float] = []
    chat_skipped: list[str] = []
    if not args.skip_chat:
        chat_latencies, chat_skipped = run_chat_benchmark(scratch_database_id, args.user_id, Path(args.chat_fixtures))

    graph_results: list[dict[str, Any]] = []
    if not args.skip_graph_scaling:
        graph_results = run_graph_scaling_benchmark()

    usage_stats = llm_extraction_service.get_usage_stats()
    _write_report(Path(args.out), ingest_results, chat_latencies, chat_skipped, graph_results, usage_stats, settings.model_name)
    print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
