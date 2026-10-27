# Pipeline Evaluation (Parser + LLM Fallback)

- Model (LLM fallback): `openai/gpt-4o-mini`
- SQL dialect: `postgres`
- Generated at: `2026-08-16T03:24:10.502608+00:00`
- Đo ở mức table (source_table, target_table), khớp mục tiêu PRD.md "Trích lineage đúng ở mức table" — không so khớp theo cột.
- Mỗi fixture chạy parser trước; parser trả rỗng mới rơi xuống LLM fallback, đúng luồng `parse_node -> llm_extract_node` của agent thật (xem `src/agents/nodes/lineage_nodes.py`).

## Per Fixture

| Fixture | Nguồn | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 01_select_simple | parser | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| 02_join_tables | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 3/4 (0.75) | missing=[]; spurious=[] |
| 03_cte_aggregate | parser | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 | 0/1 (0.00) | missing=[]; spurious=[('stg_customers', 'joined')] |
| 04_window_function | parser | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| 05_case_when | parser | 0 | 1 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_products', 'aggregated')]; spurious=[('stg_order_items', 'aggregated')] |
| 06_union_all | cache | 0 | 2 | 2 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'all_orders'), ('stg_orders_app', 'all_orders')]; spurious=[('stg_orders', '06_union_all'), ('stg_orders_app', '06_union_all')] |
| 07_dynamic_sql_fail | cache | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'mart_customer_orders')]; spurious=[] |
| 08_olist_complex | parser | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| 09_chinook_complex | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| 10_sakila_complex | parser | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| 11_alarm_quiz_lineage | parser | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| 12_alarm_face_mission_lineage | parser | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 3/3 (1.00) | missing=[]; spurious=[] |

## Corpus Micro-Average

Precision: 0.85; Recall: 0.85; F1: 0.85

Mục tiêu PRD.md (`docs/PRD.md` mục 3): Precision ≥ 0.80 và Recall ≥ 0.80 cả hai — **ĐẠT**.
