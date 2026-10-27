-- ============================================================================
-- CỐ Ý KHÔNG PARSE TĨNH ĐƯỢC — file riêng, tách khỏi warehouse_pipeline.sql.
--
-- sqlglot.parse() xử lý cả file trong 1 lần gọi: 1 statement hỏng cú pháp
-- làm hỏng việc trích xuất của TOÀN BỘ file đang chứa nó (kể cả các statement
-- hợp lệ khác trong CÙNG file) — không có cơ chế cô lập lỗi theo từng
-- statement. Vì vậy 2 case dưới đây phải nằm ở file riêng khỏi
-- warehouse_pipeline.sql.
--
-- LƯU Ý ĐÃ TỰ KIỂM CHỨNG: cả 2 case dưới đây BẾ TẮC HOÀN TOÀN với LLM luôn —
-- tên bảng/điều kiện hoàn toàn phụ thuộc biến runtime (case 1) hoặc cú pháp
-- Jinja lồng quá phức tạp (case 2) — LLM trả về `unresolved` với ĐÚNG 0 cạnh,
-- không có gì để vào hàng đợi HITL cả (không phải bug, là hành vi đúng: thà
-- không suy luận còn hơn bịa). Muốn thấy cạnh "LLM Generated" (màu cam) +
-- hàng đợi HITL thật (GET /pending-review) thực sự xuất hiện, ingest
-- llm_fallback_demo.sql (cùng thư mục) — case đó có tên bảng literal tĩnh
-- trong chuỗi SQL động nên LLM trích được cạnh confidence < 1.0 thật.
-- ============================================================================


-- Case 1: SQL động ghép chuỗi theo điều kiện runtime (kiểu ORM/dynamic SQL
-- thực tế trong production) — tên bảng/điều kiện chỉ biết lúc chạy, sqlglot
-- không có cách nào suy ra target/nguồn tĩnh.
CREATE PROCEDURE build_dynamic_customer_report(IN p_segment_filter TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    dynamic_query TEXT;
BEGIN
    dynamic_query := 'SELECT customer_id, full_name FROM dim_customers WHERE plan_tier = ''' || p_segment_filter || '''';
    IF p_segment_filter = 'enterprise' THEN
        dynamic_query := dynamic_query || ' AND current_mrr > 1000';
    END IF;
    EXECUTE dynamic_query;
END;
$$;


-- Case 2: macro kiểu dbt/Jinja CHƯA compile (vd lỡ ingest thẳng file .sql
-- nguồn của 1 dbt project thay vì bản đã compile) — cú pháp {{ }}/{% %} không
-- hợp lệ với SQL thuần, khác với {{ ref(...) }}/{{ source(...) }} đơn giản mà
-- preprocess_dbt_jinja() đã xử lý được (xem samples/jaffle-shop).
CREATE TABLE mart_legacy_placeholder AS
SELECT
    {{ dbt_utils.star(from=ref('stg_customers')) }},
    {% if var('include_churn_score', true) %}
    churn_risk_score
    {% endif %}
FROM {{ ref('mart_churn_risk_scoring') }};
