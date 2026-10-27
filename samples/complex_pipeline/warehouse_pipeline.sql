-- ============================================================================
-- CloudCart Analytics Warehouse — pipeline SQL phức tạp, nhiều lớp (900-1000
-- dòng, ~30 statement) để test thủ công qua app thật (POST /ingest, Lineage
-- Explorer, Impact Analysis, Chat Copilot). KHÔNG gắn vào bộ pytest tự động —
-- xem tests/ground_truth/sql/13_saas_analytics_pipeline.sql cho bản đó.
--
-- Miền dữ liệu: nền tảng SaaS + thương mại điện tử lai (subscription +
-- one-time order), điển hình cho 1 công ty mid-size thật. 5 lớp:
--   raw (nguồn, không tạo bảng ở đây) -> staging -> intermediate -> marts
--   -> reporting
-- Cố tình bao phủ nhiều dạng cú pháp: CTE lồng sâu (5+ tầng), window function
-- (ROW_NUMBER/RANK/LAG/LEAD/SUM OVER), JOIN nhiều loại (inner/left/self),
-- UNION ALL, CASE WHEN/COALESCE lồng nhau, subquery tương quan, recursive CTE
-- (đệ quy phân cấp nhân viên).
--
-- LƯU Ý QUAN TRỌNG: các statement "cố ý lỗi" (SQL động ghép chuỗi, macro
-- Jinja chưa compile) KHÔNG nằm trong file này — nằm ở 2 file riêng cùng thư
-- mục. Lý do: sqlglot.parse() xử lý CẢ FILE trong 1 lần gọi — 1 statement lỗi
-- cú pháp sẽ làm hỏng việc trích xuất của TOÀN BỘ file (kể cả các statement
-- hợp lệ đứng trước nó), không có cơ chế cô lập lỗi theo từng statement như
-- nhiều người kỳ vọng. Ingest cả 3 file trong thư mục samples/complex_pipeline/
-- để thấy đủ 3 trạng thái trên Lineage Explorer:
--   - warehouse_pipeline.sql (file này)         -> cạnh "Verified Flow" (xanh)
--   - dynamic_sql_and_jinja_placeholder.sql      -> bế tắc hoàn toàn, 0 cạnh,
--                                                    không vào HITL (LLM cũng
--                                                    từ chối đoán, đúng thiết kế)
--   - llm_fallback_demo.sql                      -> cạnh "LLM Generated" (cam),
--                                                    confidence < 1.0, vào
--                                                    hàng đợi HITL (GET
--                                                    /pending-review) thật
-- ============================================================================


-- ============================================================================
-- LỚP 1: STAGING — làm sạch/đổi tên 1:1 từ raw, chưa join
-- ============================================================================

CREATE TABLE stg_customers AS
SELECT
    c.customer_id,
    c.email,
    c.full_name,
    c.signup_at,
    c.country_code,
    c.referred_by_customer_id,
    CASE
        WHEN c.plan_tier IS NULL THEN 'free'
        WHEN c.plan_tier = '' THEN 'free'
        ELSE LOWER(c.plan_tier)
    END AS plan_tier,
    c.is_deleted
FROM raw.customers c
WHERE c.is_test_account = FALSE;


CREATE TABLE stg_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.ordered_at,
    o.currency,
    o.subtotal_amount,
    o.tax_amount,
    o.shipping_amount,
    o.subtotal_amount + o.tax_amount + o.shipping_amount AS order_total
FROM raw.orders o
WHERE o.order_status != 'cancelled_test';


CREATE TABLE stg_order_items AS
SELECT
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_total
FROM raw.order_items oi;


CREATE TABLE stg_products AS
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.category,
    p.cost_price,
    p.list_price,
    p.warehouse_id
FROM raw.products p
WHERE p.is_archived = FALSE;


CREATE TABLE stg_subscriptions AS
SELECT
    s.subscription_id,
    s.customer_id,
    s.plan_code,
    s.monthly_price,
    s.started_at,
    s.cancelled_at,
    CASE WHEN s.cancelled_at IS NULL THEN TRUE ELSE FALSE END AS is_active
FROM raw.subscriptions s;


CREATE TABLE stg_subscription_events AS
SELECT
    se.event_id,
    se.subscription_id,
    se.event_type,
    se.event_at,
    se.old_plan_code,
    se.new_plan_code
FROM raw.subscription_events se;


CREATE TABLE stg_payments AS
SELECT
    pm.payment_id,
    pm.customer_id,
    pm.order_id,
    pm.subscription_id,
    pm.payment_method,
    pm.amount,
    pm.paid_at,
    pm.payment_status
FROM raw.payments pm;


CREATE TABLE stg_support_tickets AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.opened_at,
    t.closed_at,
    t.priority,
    t.category,
    EXTRACT(EPOCH FROM (t.closed_at - t.opened_at)) / 3600.0 AS resolution_hours
FROM raw.support_tickets t;


CREATE TABLE stg_web_events AS
SELECT
    w.event_id,
    w.customer_id,
    w.session_id,
    w.page_path,
    w.event_at,
    w.utm_source,
    w.utm_campaign
FROM raw.web_events w
WHERE w.is_bot_traffic = FALSE;


CREATE TABLE stg_inventory_snapshots AS
SELECT
    inv.snapshot_id,
    inv.product_id,
    inv.warehouse_id,
    inv.on_hand_qty,
    inv.snapshot_date
FROM raw.inventory_snapshots inv;


-- ============================================================================
-- LỚP 2: INTERMEDIATE — join, window function, aggregation, self-join, union
-- ============================================================================

-- CTE lồng 4 tầng + window function RANK + aggregation
CREATE TABLE int_customer_order_summary AS
WITH order_lines AS (
    SELECT
        oi.order_id,
        oi.product_id,
        oi.line_total,
        p.category
    FROM stg_order_items oi
    JOIN stg_products p ON oi.product_id = p.product_id
),
order_category_totals AS (
    SELECT
        ol.order_id,
        ol.category,
        SUM(ol.line_total) AS category_total
    FROM order_lines ol
    GROUP BY ol.order_id, ol.category
),
order_dominant_category AS (
    SELECT
        oct.order_id,
        oct.category,
        oct.category_total,
        ROW_NUMBER() OVER (
            PARTITION BY oct.order_id
            ORDER BY oct.category_total DESC
        ) AS category_rank
    FROM order_category_totals oct
),
customer_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.order_total,
        o.ordered_at,
        odc.category AS dominant_category
    FROM stg_orders o
    LEFT JOIN order_dominant_category odc
        ON o.order_id = odc.order_id AND odc.category_rank = 1
)
SELECT
    co.customer_id,
    COUNT(DISTINCT co.order_id) AS lifetime_order_count,
    SUM(co.order_total) AS lifetime_order_value,
    MIN(co.ordered_at) AS first_order_at,
    MAX(co.ordered_at) AS last_order_at,
    MODE() WITHIN GROUP (ORDER BY co.dominant_category) AS favorite_category
FROM customer_orders co
GROUP BY co.customer_id;


-- Window function LAG để tính MRR delta theo từng sự kiện subscription
CREATE TABLE int_subscription_mrr AS
WITH subscription_price_history AS (
    SELECT
        s.subscription_id,
        s.customer_id,
        s.plan_code,
        s.monthly_price,
        s.started_at AS effective_at,
        s.is_active
    FROM stg_subscriptions s
),
mrr_with_lag AS (
    SELECT
        sph.subscription_id,
        sph.customer_id,
        sph.plan_code,
        sph.monthly_price,
        sph.effective_at,
        sph.is_active,
        LAG(sph.monthly_price) OVER (
            PARTITION BY sph.customer_id
            ORDER BY sph.effective_at
        ) AS previous_price,
        LEAD(sph.effective_at) OVER (
            PARTITION BY sph.customer_id
            ORDER BY sph.effective_at
        ) AS next_change_at
    FROM subscription_price_history sph
)
SELECT
    mwl.subscription_id,
    mwl.customer_id,
    mwl.plan_code,
    mwl.monthly_price,
    mwl.previous_price,
    mwl.monthly_price - COALESCE(mwl.previous_price, 0) AS mrr_delta,
    mwl.effective_at,
    mwl.next_change_at,
    mwl.is_active
FROM mrr_with_lag mwl;


-- Aggregation + window RANK cho hiệu suất sản phẩm
CREATE TABLE int_product_performance AS
WITH product_sales AS (
    SELECT
        oi.product_id,
        SUM(oi.quantity) AS units_sold,
        SUM(oi.line_total) AS gross_revenue,
        COUNT(DISTINCT oi.order_id) AS order_count
    FROM stg_order_items oi
    GROUP BY oi.product_id
),
product_margin AS (
    SELECT
        ps.product_id,
        ps.units_sold,
        ps.gross_revenue,
        ps.order_count,
        p.cost_price,
        p.list_price,
        p.category,
        ps.gross_revenue - (ps.units_sold * p.cost_price) AS gross_margin
    FROM product_sales ps
    JOIN stg_products p ON ps.product_id = p.product_id
)
SELECT
    pm.product_id,
    pm.category,
    pm.units_sold,
    pm.gross_revenue,
    pm.gross_margin,
    pm.order_count,
    RANK() OVER (PARTITION BY pm.category ORDER BY pm.gross_revenue DESC) AS category_rank,
    RANK() OVER (ORDER BY pm.gross_margin DESC) AS overall_margin_rank
FROM product_margin pm;


-- CASE WHEN lồng nhau để phân loại SLA hỗ trợ khách hàng
CREATE TABLE int_support_ticket_resolution AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.priority,
    t.category,
    t.resolution_hours,
    CASE
        WHEN t.priority = 'urgent' AND t.resolution_hours > 4 THEN 'sla_breached'
        WHEN t.priority = 'high' AND t.resolution_hours > 24 THEN 'sla_breached'
        WHEN t.priority = 'normal' AND t.resolution_hours > 72 THEN 'sla_breached'
        WHEN t.resolution_hours IS NULL THEN 'still_open'
        ELSE 'within_sla'
    END AS sla_status,
    COALESCE(t.resolution_hours, 0) AS resolution_hours_safe
FROM stg_support_tickets t;


-- UNION ALL 2 nguồn quảng cáo khác nhau rồi gắn về đơn hàng
CREATE TABLE int_marketing_attribution AS
WITH web_touchpoints AS (
    SELECT
        w.customer_id,
        w.utm_source AS channel,
        w.utm_campaign AS campaign,
        w.event_at AS touchpoint_at
    FROM stg_web_events w
    WHERE w.utm_source IS NOT NULL
),
paid_touchpoints AS (
    SELECT
        we.customer_id,
        'paid_social' AS channel,
        we.utm_campaign AS campaign,
        we.event_at AS touchpoint_at
    FROM stg_web_events we
    WHERE we.page_path = '/landing/paid'
),
all_touchpoints AS (
    SELECT customer_id, channel, campaign, touchpoint_at FROM web_touchpoints
    UNION ALL
    SELECT customer_id, channel, campaign, touchpoint_at FROM paid_touchpoints
),
last_touch AS (
    SELECT
        at.customer_id,
        at.channel,
        at.campaign,
        ROW_NUMBER() OVER (
            PARTITION BY at.customer_id
            ORDER BY at.touchpoint_at DESC
        ) AS touch_rank
    FROM all_touchpoints at
)
SELECT
    lt.customer_id,
    lt.channel AS last_touch_channel,
    lt.campaign AS last_touch_campaign,
    o.order_id,
    o.order_total
FROM last_touch lt
JOIN stg_orders o ON lt.customer_id = o.customer_id
WHERE lt.touch_rank = 1;


-- Self-join để dựng chuỗi giới thiệu khách hàng (referral chain)
CREATE TABLE int_customer_referrals AS
SELECT
    referred.customer_id AS referred_customer_id,
    referred.full_name AS referred_customer_name,
    referrer.customer_id AS referrer_customer_id,
    referrer.full_name AS referrer_customer_name,
    referrer.plan_tier AS referrer_plan_tier,
    referred.signup_at AS referred_signup_at
FROM stg_customers referred
LEFT JOIN stg_customers referrer
    ON referred.referred_by_customer_id = referrer.customer_id;


-- Window function running SUM cho tồn kho
CREATE TABLE int_inventory_turnover AS
WITH daily_snapshots AS (
    SELECT
        inv.product_id,
        inv.warehouse_id,
        inv.snapshot_date,
        inv.on_hand_qty,
        LAG(inv.on_hand_qty) OVER (
            PARTITION BY inv.product_id, inv.warehouse_id
            ORDER BY inv.snapshot_date
        ) AS previous_qty
    FROM stg_inventory_snapshots inv
),
daily_delta AS (
    SELECT
        ds.product_id,
        ds.warehouse_id,
        ds.snapshot_date,
        ds.on_hand_qty,
        ds.on_hand_qty - COALESCE(ds.previous_qty, ds.on_hand_qty) AS qty_delta
    FROM daily_snapshots ds
)
SELECT
    dd.product_id,
    dd.warehouse_id,
    dd.snapshot_date,
    dd.on_hand_qty,
    dd.qty_delta,
    SUM(dd.qty_delta) OVER (
        PARTITION BY dd.product_id, dd.warehouse_id
        ORDER BY dd.snapshot_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_qty_delta
FROM daily_delta dd;


-- Recursive CTE — phân cấp nhân viên (stress-test parser với đệ quy)
CREATE TABLE int_employee_hierarchy AS
WITH RECURSIVE employee_chain AS (
    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        e.department,
        1 AS depth
    FROM raw.employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        e.department,
        ec.depth + 1 AS depth
    FROM raw.employees e
    JOIN employee_chain ec ON e.manager_id = ec.employee_id
)
SELECT
    ec.employee_id,
    ec.full_name,
    ec.manager_id,
    ec.department,
    ec.depth
FROM employee_chain ec;


-- ============================================================================
-- LỚP 3: MARTS — kết hợp nhiều bảng intermediate thành bảng phân tích rộng
-- ============================================================================

-- Dim khách hàng 360 độ — join rộng 5 bảng intermediate
CREATE TABLE dim_customers AS
SELECT
    c.customer_id,
    c.email,
    c.full_name,
    c.country_code,
    c.plan_tier,
    c.signup_at,
    cos.lifetime_order_count,
    cos.lifetime_order_value,
    cos.favorite_category,
    smrr.monthly_price AS current_mrr,
    smrr.is_active AS has_active_subscription,
    cr.referrer_customer_id,
    cr.referrer_plan_tier,
    COUNT(DISTINCT tr.ticket_id) AS total_support_tickets,
    SUM(CASE WHEN tr.sla_status = 'sla_breached' THEN 1 ELSE 0 END) AS sla_breach_count
FROM stg_customers c
LEFT JOIN int_customer_order_summary cos ON c.customer_id = cos.customer_id
LEFT JOIN int_subscription_mrr smrr ON c.customer_id = smrr.customer_id AND smrr.is_active = TRUE
LEFT JOIN int_customer_referrals cr ON c.customer_id = cr.referred_customer_id
LEFT JOIN int_support_ticket_resolution tr ON c.customer_id = tr.customer_id
GROUP BY
    c.customer_id, c.email, c.full_name, c.country_code, c.plan_tier, c.signup_at,
    cos.lifetime_order_count, cos.lifetime_order_value, cos.favorite_category,
    smrr.monthly_price, smrr.is_active, cr.referrer_customer_id, cr.referrer_plan_tier;


-- Fact doanh thu theo ngày — UNION doanh thu subscription + doanh thu order
CREATE TABLE fct_revenue_daily AS
WITH subscription_revenue AS (
    SELECT
        DATE_TRUNC('day', pm.paid_at) AS revenue_date,
        'subscription' AS revenue_source,
        SUM(pm.amount) AS daily_amount
    FROM stg_payments pm
    WHERE pm.subscription_id IS NOT NULL AND pm.payment_status = 'succeeded'
    GROUP BY DATE_TRUNC('day', pm.paid_at)
),
order_revenue AS (
    SELECT
        DATE_TRUNC('day', pm.paid_at) AS revenue_date,
        'one_time_order' AS revenue_source,
        SUM(pm.amount) AS daily_amount
    FROM stg_payments pm
    WHERE pm.order_id IS NOT NULL AND pm.payment_status = 'succeeded'
    GROUP BY DATE_TRUNC('day', pm.paid_at)
),
combined_revenue AS (
    SELECT revenue_date, revenue_source, daily_amount FROM subscription_revenue
    UNION ALL
    SELECT revenue_date, revenue_source, daily_amount FROM order_revenue
)
SELECT
    cr.revenue_date,
    cr.revenue_source,
    cr.daily_amount,
    SUM(cr.daily_amount) OVER (
        PARTITION BY cr.revenue_source
        ORDER BY cr.revenue_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_amount
FROM combined_revenue cr;


-- Cohort retention — window function theo tháng cohort
CREATE TABLE mart_cohort_retention AS
WITH customer_cohort AS (
    SELECT
        c.customer_id,
        DATE_TRUNC('month', c.signup_at) AS cohort_month
    FROM stg_customers c
),
customer_activity_month AS (
    SELECT
        o.customer_id,
        DATE_TRUNC('month', o.ordered_at) AS activity_month
    FROM stg_orders o
    GROUP BY o.customer_id, DATE_TRUNC('month', o.ordered_at)
),
cohort_activity AS (
    SELECT
        cc.customer_id,
        cc.cohort_month,
        cam.activity_month,
        EXTRACT(
            YEAR FROM AGE(cam.activity_month, cc.cohort_month)
        ) * 12 + EXTRACT(MONTH FROM AGE(cam.activity_month, cc.cohort_month)) AS months_since_signup
    FROM customer_cohort cc
    JOIN customer_activity_month cam ON cc.customer_id = cam.customer_id
)
SELECT
    ca.cohort_month,
    ca.months_since_signup,
    COUNT(DISTINCT ca.customer_id) AS active_customers,
    RANK() OVER (
        PARTITION BY ca.cohort_month
        ORDER BY ca.months_since_signup
    ) AS month_sequence
FROM cohort_activity ca
GROUP BY ca.cohort_month, ca.months_since_signup;


-- Chấm điểm rủi ro churn — CASE WHEN nhiều tầng + subquery tương quan
CREATE TABLE mart_churn_risk_scoring AS
SELECT
    dc.customer_id,
    dc.full_name,
    dc.plan_tier,
    dc.current_mrr,
    dc.total_support_tickets,
    dc.sla_breach_count,
    CASE
        WHEN dc.has_active_subscription = FALSE THEN 100
        WHEN dc.sla_breach_count >= 3 THEN 80
        WHEN dc.lifetime_order_count = 0 AND dc.current_mrr IS NOT NULL THEN 60
        WHEN (
            SELECT MAX(se.event_at)
            FROM stg_subscription_events se
            WHERE se.subscription_id IN (
                SELECT s.subscription_id FROM stg_subscriptions s WHERE s.customer_id = dc.customer_id
            )
            AND se.event_type = 'downgrade'
        ) IS NOT NULL THEN 40
        ELSE 10
    END AS churn_risk_score,
    CASE
        WHEN dc.sla_breach_count >= 3 THEN 'support_friction'
        WHEN dc.lifetime_order_count = 0 THEN 'never_purchased'
        ELSE 'healthy'
    END AS churn_risk_reason
FROM dim_customers dc;


-- Customer 360 — mart cuối, join tất cả mart/intermediate liên quan
CREATE TABLE mart_customer_360 AS
SELECT
    dc.customer_id,
    dc.email,
    dc.full_name,
    dc.plan_tier,
    dc.lifetime_order_value,
    dc.current_mrr,
    crs.churn_risk_score,
    crs.churn_risk_reason,
    ma.last_touch_channel,
    ma.last_touch_campaign,
    pp.category_rank AS favorite_category_product_rank
FROM dim_customers dc
LEFT JOIN mart_churn_risk_scoring crs ON dc.customer_id = crs.customer_id
LEFT JOIN int_marketing_attribution ma ON dc.customer_id = ma.customer_id
LEFT JOIN int_product_performance pp ON dc.favorite_category = pp.category AND pp.category_rank = 1;


-- KPI điều hành — aggregation của aggregation (subquery trong FROM)
CREATE TABLE mart_executive_kpis AS
SELECT
    kpi_month.month,
    kpi_month.total_revenue,
    kpi_month.active_customer_count,
    kpi_month.avg_churn_risk_score
FROM (
    SELECT
        DATE_TRUNC('month', frd.revenue_date) AS month,
        SUM(frd.daily_amount) AS total_revenue,
        COUNT(DISTINCT dc.customer_id) AS active_customer_count,
        AVG(crs.churn_risk_score) AS avg_churn_risk_score
    FROM fct_revenue_daily frd
    CROSS JOIN dim_customers dc
    LEFT JOIN mart_churn_risk_scoring crs ON dc.customer_id = crs.customer_id
    GROUP BY DATE_TRUNC('month', frd.revenue_date)
) kpi_month;


-- ROI marketing — join spend + doanh thu quy đổi
CREATE TABLE mart_marketing_roi AS
WITH campaign_spend AS (
    SELECT
        a.campaign_name,
        a.channel,
        SUM(a.spend_amount) AS total_spend
    FROM raw.ad_spend a
    GROUP BY a.campaign_name, a.channel
),
campaign_revenue AS (
    SELECT
        ma.last_touch_campaign AS campaign_name,
        ma.last_touch_channel AS channel,
        SUM(ma.order_total) AS attributed_revenue
    FROM int_marketing_attribution ma
    GROUP BY ma.last_touch_campaign, ma.last_touch_channel
)
SELECT
    cs.campaign_name,
    cs.channel,
    cs.total_spend,
    COALESCE(cr.attributed_revenue, 0) AS attributed_revenue,
    CASE
        WHEN cs.total_spend = 0 THEN NULL
        ELSE COALESCE(cr.attributed_revenue, 0) / cs.total_spend
    END AS roi_ratio
FROM campaign_spend cs
LEFT JOIN campaign_revenue cr
    ON cs.campaign_name = cr.campaign_name AND cs.channel = cr.channel;


-- Sức khoẻ tồn kho — join turnover + product performance
CREATE TABLE mart_inventory_health AS
SELECT
    it.product_id,
    it.warehouse_id,
    it.snapshot_date,
    it.on_hand_qty,
    it.running_qty_delta,
    pp.units_sold,
    pp.category,
    CASE
        WHEN it.on_hand_qty = 0 THEN 'out_of_stock'
        WHEN it.on_hand_qty < pp.units_sold * 0.1 THEN 'low_stock'
        WHEN it.running_qty_delta < 0 AND ABS(it.running_qty_delta) > pp.units_sold THEN 'overselling_risk'
        ELSE 'healthy'
    END AS stock_status
FROM int_inventory_turnover it
JOIN int_product_performance pp ON it.product_id = pp.product_id;


-- ============================================================================
-- LỚP 4: REPORTING — bảng phục vụ BI/dashboard trực tiếp
-- ============================================================================

CREATE OR REPLACE VIEW rpt_customer_health_dashboard AS
SELECT
    m360.customer_id,
    m360.full_name,
    m360.plan_tier,
    m360.current_mrr,
    m360.churn_risk_score,
    m360.churn_risk_reason,
    eh.full_name AS account_owner_name,
    eh.department AS account_owner_department
FROM mart_customer_360 m360
LEFT JOIN int_employee_hierarchy eh ON eh.department = 'customer_success' AND eh.depth = 2;


CREATE OR REPLACE VIEW rpt_monthly_business_review AS
SELECT
    ek.month,
    ek.total_revenue,
    ek.active_customer_count,
    ek.avg_churn_risk_score,
    (
        SELECT SUM(mroi.attributed_revenue)
        FROM mart_marketing_roi mroi
    ) AS total_attributed_marketing_revenue
FROM mart_executive_kpis ek
ORDER BY ek.month DESC;
