# Pipeline Evaluation (Parser + LLM Fallback)

- Model (LLM fallback): `openai/gpt-4o-mini`
- SQL dialect: `postgres`
- Mode: `hybrid` (hybrid = parser trước, LLM fallback chỉ khi parser rỗng — đúng luồng agent thật; parser_only = bỏ hẳn LLM fallback; llm_only = luôn ép qua LLM bất kể parser thành công hay không, để so sánh 3 cách tiếp cận trên cùng 1 corpus)
- Generated at: `2026-08-31T16:04:55.374405+00:00`
- Đo ở mức table (source_table, target_table), khớp mục tiêu PRD.md "Trích lineage đúng ở mức table" — xem thêm section Column-Level Micro-Average bên dưới cho phép đo nghiêm ngặt hơn (mức cột).
- Mỗi fixture chạy parser trước; parser trả rỗng mới rơi xuống LLM fallback, đúng luồng `parse_node -> llm_extract_node` của agent thật (xem `src/agents/nodes/lineage_nodes.py`) — chỉ áp dụng khi mode=hybrid.

## Per Fixture

| Fixture | Nguồn | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 01_select_simple | parser | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| 02_join_tables | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 3/4 (0.75) | missing=[]; spurious=[] |
| 03_cte_aggregate | parser | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 | 0/1 (0.00) | missing=[]; spurious=[('stg_customers', 'joined')] |
| 04_window_function | parser | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/1 (0.00) | missing=[]; spurious=[] |
| 05_case_when | parser | 0 | 1 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_products', 'aggregated')]; spurious=[('stg_order_items', 'aggregated')] |
| 06_union_all | parser | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| 07_dynamic_sql_fail | cache | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'mart_customer_orders')]; spurious=[] |
| 08_olist_complex | parser | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| 09_chinook_complex | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| 10_sakila_complex | parser | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| 11_alarm_quiz_lineage | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| 12_alarm_face_mission_lineage | parser | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 3/3 (1.00) | missing=[]; spurious=[] |
| 13_saas_analytics_pipeline | parser | 12 | 1 | 0 | 0.92 | 1.00 | 0.96 | 9/12 (0.75) | missing=[]; spurious=[('stg_orders', 'mart_vip_flag')] |

## Corpus Micro-Average

Precision: 0.92; Recall: 0.95; F1: 0.94

Mục tiêu PRD.md (`docs/PRD.md` mục 3): Precision ≥ 0.80 và Recall ≥ 0.80 cả hai — **ĐẠT**.

## Column-Level Micro-Average

Precision: 0.57; Recall: 0.88; F1: 0.69

So khớp nghiêm ngặt ở mức `(source_table, source_column, target_table, target_column)` — không phải mục tiêu PRD (chỉ yêu cầu mức table), chỉ mang tính tham khảo mở rộng. **Lưu ý**: fixture nào có toàn `source_column`/`target_column` = null ở cả 2 phía sẽ so khớp bằng key rỗng — không phải bằng chứng thật về độ chính xác cấp cột, chỉ fixture nào thật sự khai báo cột (vd `13_saas_analytics_pipeline.json`) mới có ý nghĩa đo lường ở đây.

## Confidence Threshold Sweep

Quét ngưỡng `confidence_threshold` (src/config.py) trên đúng tập cạnh dự đoán của mode hiện tại — trả lời câu hỏi PRD.md mục 11 (rủi ro): "ngưỡng 0.8 chưa có cơ sở thực nghiệm".

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 0.92 | 0.95 | 0.94 |
| 0.60 | 0.92 | 0.95 | 0.94 |
| 0.70 | 0.92 | 0.95 | 0.94 |
| 0.80 | 0.92 | 0.95 | 0.94 |
| 0.90 | 0.92 | 0.95 | 0.94 |
