# Evaluation

Ba loại bằng chứng, đo 3 thứ khác nhau:

- `run_extraction_eval.py` — đo **riêng** chất lượng LLM extraction trên `tests/ground_truth/llm/` (dùng để tune prompt/threshold, không đụng tới parser). Dùng chung `eval/metrics.py`.
- `run_pipeline_eval.py` — đo **toàn bộ agent** (parser trước, LLM fallback khi parser rỗng) trên `tests/ground_truth/sql/` — con số khớp thẳng với mục tiêu SMART trong `docs/PRD.md` mục 3 ("Trích lineage đúng ở mức table, Precision/Recall ≥ 80% cả hai"). Dùng chung `eval/metrics.py`.
- [`manual_test_cases.md`](manual_test_cases.md) — **test tay thật trên sản phẩm cuối** (click UI thật, không gọi API bằng tay) theo format Test ID/Steps/Pre-conditions/Expected/Actual/Status, kèm ảnh chụp màn hình thật từng bước ([`manual_test_screenshots/`](manual_test_screenshots/)). Gồm cả regression test cho 2 bug thật đã phát hiện và fix (PR #43, #45).

## LLM Extraction Evaluation

Run cached fixtures without network access:

```bash
./.venv/bin/python -m eval.run_extraction_eval
```

## Pipeline Evaluation (parser + LLM fallback)

```bash
./.venv/bin/python -m eval.run_pipeline_eval
```

Cả hai: nếu 1 fixture thiếu trong cache, lệnh thoát khác 0 và liệt kê tên fixture đó. Thêm `--live` để cho phép gọi API thật với key đã cấu hình; `--refresh` bỏ qua cache cũ (bắt buộc đi kèm `--live`). Report ghi vào `eval/results/`.

`run_pipeline_eval.py` còn hỗ trợ `--mode {hybrid,parser_only,llm_only}` (so sánh 3 cách tiếp cận trên cùng corpus) và `--thresholds` (quét ngưỡng confidence) — xem [`docs/comparative_research.md`](../docs/comparative_research.md) cho phân tích nội bộ (parser vs LLM vs hybrid) + so sánh với OpenMetadata/DataHub/Atlan, và [`run_performance_benchmark.py`](run_performance_benchmark.py) (`python -m eval.run_performance_benchmark --user-id <id>`) cho số liệu hiệu năng thật (ingest latency, chat latency, chi phí LLM, graph-size scaling) — kết quả ở `eval/results/performance_benchmark.md`.

The cache at `eval/.cache/` contains model responses and should not be committed. Ground truth is hand-authored by the extractor owner, so its metrics measure agreement with these labels rather than independent real-world correctness.
