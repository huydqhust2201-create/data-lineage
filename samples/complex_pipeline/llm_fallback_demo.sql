-- ============================================================================
-- Demo nhánh LLM fallback THÀNH CÔNG (khác dynamic_sql_and_jinja_placeholder.sql
-- — file đó cố tình bế tắc hoàn toàn, LLM trả unresolved, 0 cạnh, không có gì
-- để vào HITL). File này ngược lại: sqlglot vẫn parse tĩnh thất bại (cú pháp
-- PL/pgSQL + ghép chuỗi), nhưng TÊN BẢNG là literal tĩnh trong chuỗi SQL động
-- — chỉ điều kiện lọc (WHERE) phụ thuộc biến runtime. Theo đúng rule của
-- prompt LLM extraction (llm_extraction_service.py: "nếu chuỗi chứa tên bảng
-- literal tĩnh, không gắn biến, thì trích xuất"), LLM sẽ suy luận ra cạnh
-- thật với confidence < 1.0 (source_type="llm") — cạnh này sẽ hiện màu "LLM
-- Generated" trên Lineage Explorer và rơi vào GET /pending-review (HITL
-- Queue) chờ duyệt, đúng luồng FR-3 + HITL của PRD.
-- ============================================================================

CREATE OR REPLACE PROCEDURE refresh_regional_sales_mart(IN p_region TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql := 'INSERT INTO mart_regional_sales
               SELECT region, SUM(amount) AS total_amount
               FROM raw.regional_orders
               WHERE region = ''' || p_region || '''
               GROUP BY region';
    EXECUTE v_sql;
END;
$$;


CREATE OR REPLACE PROCEDURE refresh_channel_conversion_summary(IN p_channel TEXT, IN p_start_date DATE)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql := 'CREATE OR REPLACE TABLE mart_channel_conversion AS
               SELECT channel, COUNT(*) AS conversion_count
               FROM raw.web_events
               WHERE channel = ''' || p_channel || '''
               AND event_at >= ''' || p_start_date || '''
               GROUP BY channel';
    EXECUTE v_sql;
END;
$$;
