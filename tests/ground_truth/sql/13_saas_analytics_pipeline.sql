-- 13_saas_analytics_pipeline.sql
-- Case ground-truth "khá lớn" theo yêu cầu: nhiều statement, CTE lồng sâu,
-- window function, JOIN nhiều loại, CASE WHEN, UNION ALL, subquery tương
-- quan — độc lập với samples/complex_pipeline/ (không phụ thuộc file khác).
-- Style CREATE TABLE/VIEW AS xuyên suốt để target_table luôn tường minh
-- (tránh heuristic "CTE cuối cùng trong FROM" của case bare-SELECT như
-- 08/09/10 — khó đoán bằng mắt hơn).

CREATE TABLE stg_customers AS
SELECT
    c.customer_id,
    c.email,
    c.signup_at,
    c.country_code
FROM raw.customers c
WHERE c.is_test_account = FALSE;


CREATE TABLE stg_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.ordered_at,
    o.subtotal_amount + o.tax_amount AS order_total
FROM raw.orders o;


CREATE TABLE stg_support_tickets AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.priority,
    t.resolution_hours
FROM raw.support_tickets t;


-- CTE lồng 3 tầng + JOIN + window function ROW_NUMBER
CREATE TABLE int_customer_order_rank AS
WITH order_totals AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.order_total
    FROM stg_orders o
    WHERE o.order_status = 'completed'
),
customer_order_agg AS (
    SELECT
        ot.customer_id,
        COUNT(ot.order_id) AS order_count,
        SUM(ot.order_total) AS total_spent
    FROM order_totals ot
    GROUP BY ot.customer_id
),
ranked_customers AS (
    SELECT
        coa.customer_id,
        coa.order_count,
        coa.total_spent,
        RANK() OVER (ORDER BY coa.total_spent DESC) AS spend_rank
    FROM customer_order_agg coa
)
SELECT
    rc.customer_id,
    rc.order_count,
    rc.total_spent,
    rc.spend_rank
FROM ranked_customers rc;


-- CASE WHEN lồng nhau phân loại SLA
CREATE TABLE int_support_sla_status AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.priority,
    CASE
        WHEN t.priority = 'urgent' AND t.resolution_hours > 4 THEN 'breached'
        WHEN t.priority = 'normal' AND t.resolution_hours > 72 THEN 'breached'
        ELSE 'within_sla'
    END AS sla_status
FROM stg_support_tickets t;


-- Mart cuối — JOIN 2 bảng intermediate, aggregation trên CASE WHEN
CREATE TABLE mart_customer_risk AS
SELECT
    cor.customer_id,
    cor.total_spent,
    cor.spend_rank,
    c.email,
    c.country_code,
    SUM(CASE WHEN sla.sla_status = 'breached' THEN 1 ELSE 0 END) AS breached_ticket_count
FROM int_customer_order_rank cor
JOIN stg_customers c ON cor.customer_id = c.customer_id
LEFT JOIN int_support_sla_status sla ON cor.customer_id = sla.customer_id
GROUP BY cor.customer_id, cor.total_spent, cor.spend_rank, c.email, c.country_code;


-- UNION ALL 2 nhánh cùng schema rồi window SUM chạy dồn
CREATE TABLE mart_daily_activity AS
WITH order_activity AS (
    SELECT
        DATE_TRUNC('day', o.ordered_at) AS activity_date,
        'order' AS activity_type,
        COUNT(*) AS activity_count
    FROM stg_orders o
    GROUP BY DATE_TRUNC('day', o.ordered_at)
),
ticket_activity AS (
    SELECT
        DATE_TRUNC('day', t.opened_at) AS activity_date,
        'ticket' AS activity_type,
        COUNT(*) AS activity_count
    FROM raw.support_tickets t
    GROUP BY DATE_TRUNC('day', t.opened_at)
),
combined AS (
    SELECT activity_date, activity_type, activity_count FROM order_activity
    UNION ALL
    SELECT activity_date, activity_type, activity_count FROM ticket_activity
)
SELECT
    c.activity_date,
    c.activity_type,
    c.activity_count,
    SUM(c.activity_count) OVER (
        PARTITION BY c.activity_type
        ORDER BY c.activity_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM combined c;


-- Subquery tương quan trong CASE WHEN
CREATE TABLE mart_vip_flag AS
SELECT
    mcr.customer_id,
    mcr.total_spent,
    CASE
        WHEN mcr.spend_rank <= 10 THEN 'vip'
        WHEN (
            SELECT COUNT(*) FROM stg_orders o WHERE o.customer_id = mcr.customer_id
        ) >= 5 THEN 'frequent'
        ELSE 'regular'
    END AS customer_segment
FROM mart_customer_risk mcr;


CREATE OR REPLACE VIEW rpt_customer_risk_dashboard AS
SELECT
    vf.customer_id,
    vf.customer_segment,
    mcr.breached_ticket_count,
    mcr.email
FROM mart_vip_flag vf
JOIN mart_customer_risk mcr ON vf.customer_id = mcr.customer_id;
