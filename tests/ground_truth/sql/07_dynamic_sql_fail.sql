-- 07_dynamic_sql_fail.sql
-- Dynamic SQL: tên bảng + cột được truyền lúc runtime
-- sqlglot / sqllineage sẽ fail hoàn toàn (không trích được lineage)

CREATE OR REPLACE PROCEDURE load_customer_orders(
    source_table STRING,      -- ví dụ: 'stg_orders'
    date_column  STRING,      -- ví dụ: 'ordered_at'
    amount_column STRING      -- ví dụ: 'order_total'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    EXECUTE IMMEDIATE '
        CREATE OR REPLACE TABLE mart_customer_orders AS
        SELECT
            customer_id,
            ' || date_column || ' AS order_date,
            SUM(' || amount_column || ') AS total_amount,
            COUNT(*) AS order_count
        FROM ' || source_table || '
        WHERE status = ''completed''
        GROUP BY customer_id, ' || date_column || '
    ';

    RETURN 'loaded from ' || source_table;
END;
$$;

-- Gọi procedure (lúc runtime mới biết giá trị thật)
CALL load_customer_orders('stg_orders', 'ordered_at', 'order_total');