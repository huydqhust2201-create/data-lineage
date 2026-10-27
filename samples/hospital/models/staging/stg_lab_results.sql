CREATE TABLE stg_lab_results AS (
    WITH orders AS (
        SELECT * FROM raw_lab_orders
    ),
    results AS (
        SELECT * FROM raw_lab_results
    )
    SELECT
        orders.order_id,
        orders.patient_id,
        results.test_name,
        results.result_value,
        results.is_abnormal
    FROM orders
    JOIN results ON orders.order_id = results.order_id
);
