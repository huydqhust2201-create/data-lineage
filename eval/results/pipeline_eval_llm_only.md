# Pipeline Evaluation (Parser + LLM Fallback)

- Model (LLM fallback): `openai/gpt-4o-mini`
- SQL dialect: `postgres`
- Mode: `llm_only` (hybrid = parser trước, LLM fallback chỉ khi parser rỗng — đúng luồng agent thật; parser_only = bỏ hẳn LLM fallback; llm_only = luôn ép qua LLM bất kể parser thành công hay không, để so sánh 3 cách tiếp cận trên cùng 1 corpus)
- Generated at: `2026-08-31T16:10:39.768037+00:00`
- Đo ở mức table (source_table, target_table), khớp mục tiêu PRD.md "Trích lineage đúng ở mức table" — xem thêm section Column-Level Micro-Average bên dưới cho phép đo nghiêm ngặt hơn (mức cột).
- Mỗi fixture chạy parser trước; parser trả rỗng mới rơi xuống LLM fallback, đúng luồng `parse_node -> llm_extract_node` của agent thật (xem `src/agents/nodes/lineage_nodes.py`) — chỉ áp dụng khi mode=hybrid.

## Per Fixture

| Fixture | Nguồn | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 01_select_simple | live | 0 | 1 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('raw_customers', 'renamed')]; spurious=[('raw_customers', '01_select_simple')] |
| 02_join_tables | live | 0 | 4 | 4 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_order_items', 'joined'), ('stg_orders', 'joined'), ('stg_products', 'joined'), ('stg_supplies', 'joined')]; spurious=[('stg_order_items', '02_join_tables'), ('stg_orders', '02_join_tables'), ('stg_products', '02_join_tables'), ('stg_supplies', '02_join_tables')] |
| 03_cte_aggregate | live | 0 | 4 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('orders', 'joined')]; spurious=[('customer_orders_summary', '03_cte_aggregate'), ('customers', '03_cte_aggregate'), ('orders', '03_cte_aggregate'), ('stg_customers', '03_cte_aggregate')] |
| 04_window_function | live | 0 | 1 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'customer_order_count')]; spurious=[('stg_orders', '04_window_function')] |
| 05_case_when | live | 0 | 2 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_products', 'aggregated')]; spurious=[('stg_order_items', '05_case_when'), ('stg_products', '05_case_when')] |
| 06_union_all | live | 0 | 2 | 2 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'all_orders'), ('stg_orders_app', 'all_orders')]; spurious=[('stg_orders', '06_union_all'), ('stg_orders_app', '06_union_all')] |
| 07_dynamic_sql_fail | cache | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 | n/a | missing=[('stg_orders', 'mart_customer_orders')]; spurious=[] |
| 08_olist_complex | live | 0 | 4 | 2 | 0.00 | 0.00 | 0.00 | n/a | missing=[('items', 'top_sellers'), ('sellers', 'top_sellers')]; spurious=[('items', '08_olist_complex'), ('seller_review_stats', '08_olist_complex'), ('sellers', '08_olist_complex'), ('top_sellers', '08_olist_complex')] |
| 09_chinook_complex | live | 0 | 4 | 4 | 0.00 | 0.00 | 0.00 | n/a | missing=[('customer', 'target_vip_customers'), ('employee', 'target_vip_customers'), ('invoice_line', 'target_vip_customers'), ('track', 'target_vip_customers')]; spurious=[('customer', '09_chinook_complex'), ('employee', '09_chinook_complex'), ('invoice_items', '09_chinook_complex'), ('track_album_genre', '09_chinook_complex')] |
| 10_sakila_complex | live | 0 | 5 | 2 | 0.00 | 0.00 | 0.00 | n/a | missing=[('actor', 'top_actor_films'), ('customer', 'top_actor_films')]; spurious=[('actor', '10_sakila_complex'), ('customer', '10_sakila_complex'), ('film', '10_sakila_complex'), ('payment', '10_sakila_complex'), ('rental', '10_sakila_complex')] |
| 11_alarm_quiz_lineage | live | 0 | 11 | 4 | 0.00 | 0.00 | 0.00 | n/a | missing=[('alarm', 'user_progress_summary'), ('history', 'user_progress_summary'), ('questionprogress', 'user_progress_summary'), ('user', 'user_progress_summary')]; spurious=[('alarm', '11_alarm_quiz_lineage'), ('alarmtopiclink', '11_alarm_quiz_lineage'), ('history', '11_alarm_quiz_lineage'), ('question', '11_alarm_quiz_lineage'), ('questionprogress', '11_alarm_quiz_lineage'), ('ranked_topic_performance', '11_alarm_quiz_lineage'), ('topic', '11_alarm_quiz_lineage'), ('topicstats', '11_alarm_quiz_lineage'), ('user', '11_alarm_quiz_lineage'), ('user_progress_summary', '11_alarm_quiz_lineage'), ('user_question_history', '11_alarm_quiz_lineage')] |
| 12_alarm_face_mission_lineage | live | 0 | 6 | 3 | 0.00 | 0.00 | 0.00 | n/a | missing=[('alarm', 'ranked_user_memories'), ('user', 'ranked_user_memories'), ('userstats', 'ranked_user_memories')]; spurious=[('alarm', '12_alarm_face_mission_lineage'), ('alarmfacemissionconfig', '12_alarm_face_mission_lineage'), ('alarmhistory', '12_alarm_face_mission_lineage'), ('picture', '12_alarm_face_mission_lineage'), ('user', '12_alarm_face_mission_lineage'), ('userstats', '12_alarm_face_mission_lineage')] |
| 13_saas_analytics_pipeline | live | 11 | 1 | 1 | 0.92 | 0.92 | 0.92 | 9/11 (0.82) | missing=[('stg_support_tickets', 'int_support_sla_status')]; spurious=[('raw.support_tickets', 'mart_daily_activity')] |

## Corpus Micro-Average

Precision: 0.20; Recall: 0.29; F1: 0.23

Mục tiêu PRD.md (`docs/PRD.md` mục 3): Precision ≥ 0.80 và Recall ≥ 0.80 cả hai — **CHƯA ĐẠT**.

## Column-Level Micro-Average

Precision: 0.10; Recall: 0.15; F1: 0.12

So khớp nghiêm ngặt ở mức `(source_table, source_column, target_table, target_column)` — không phải mục tiêu PRD (chỉ yêu cầu mức table), chỉ mang tính tham khảo mở rộng. **Lưu ý**: fixture nào có toàn `source_column`/`target_column` = null ở cả 2 phía sẽ so khớp bằng key rỗng — không phải bằng chứng thật về độ chính xác cấp cột, chỉ fixture nào thật sự khai báo cột (vd `13_saas_analytics_pipeline.json`) mới có ý nghĩa đo lường ở đây.

## Confidence Threshold Sweep

Quét ngưỡng `confidence_threshold` (src/config.py) trên đúng tập cạnh dự đoán của mode hiện tại — trả lời câu hỏi PRD.md mục 11 (rủi ro): "ngưỡng 0.8 chưa có cơ sở thực nghiệm".

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 0.20 | 0.29 | 0.23 |
| 0.60 | 0.20 | 0.29 | 0.23 |
| 0.70 | 0.20 | 0.29 | 0.23 |
| 0.80 | 0.22 | 0.29 | 0.25 |
| 0.90 | 0.22 | 0.29 | 0.25 |
