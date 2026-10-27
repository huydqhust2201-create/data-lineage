# Performance Benchmark (số liệu thật, chạy cục bộ)

- Model: `openai/gpt-4o-mini`
- Git revision: `fff9e8cd28e7ae2affc2abc5402ed9851371b35b`
- Generated at: `2026-08-31T16:37:00.334352+00:00`
- Chưa deploy thật (README: "chưa deploy — kế hoạch W4-W5") — số liệu dưới đây đo trên máy dev, KHÔNG phải benchmark production thật, chỉ phục vụ báo cáo/pitch có số liệu thật thay vì ước lượng.

## 1. Ingest Latency theo kích thước input

| Input | Elapsed (s) | SQL files | Parsed edges | Pending review |
| --- | ---: | ---: | ---: | ---: |
| `samples/jaffle-shop` | 62.317 | 15 | 45 | 0 |
| `samples/complex_pipeline` | 176.976 | 3 | 220 | 2 |
| `samples/hospital` | 84.558 | 23 | 54 | 29 |

## 2. Chat Turn Latency (p50/p95)

- Số case đo được: 6 (bỏ qua 4 case vì database chưa có đủ bảng yêu cầu: 01_lineage_revenue_alerts_final, 02_diagnose_revenue_alerts, 04_column_projected_revenue, 06_preview_ddl_impact)
- p50: 11.16s; p95: 30.12s; min: 6.97s; max: 30.12s

## 3. Chi phí LLM ước tính (dựa trên token usage thật)

- Số lần gọi LLM extraction đo được trong lượt chạy này: 12
- Tổng token: 77255 prompt + 6874 completion = 84129 tokens
- Ước tính chi phí: $0.01571 (giá OpenRouter `openai/gpt-4o-mini`: $0.15/1M prompt + $0.6/1M completion, tra cứu 2026-08-31 (tự tra cứu, cần xác minh lại) — **kiểm tra lại giá trước khi dùng cho tài liệu chính thức**)

## 4. Graph-Size Scaling (Impact Query)

Tái dùng `_build_wide_deep_graph()` từ `tests/test_services/test_impact_latency.py` (đồ thị tổng hợp, KHÔNG phải dữ liệu demo thật) — mục tiêu PRD: impact query < 3s.

| Depth | Fanout | Confirmed edges | Elapsed (s) | < 3s (PRD)? |
| ---: | ---: | ---: | ---: | :---: |
| 4 | 6 | 114 | 0.003 | ✅ |
| 6 | 9 | 414 | 0.006 | ✅ |
| 8 | 12 | 1020 | 0.016 | ✅ |
