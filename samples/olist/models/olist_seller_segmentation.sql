{{ config(
    materialized='table',
    schema='analytics'
) }}

WITH seller_revenues AS (
    SELECT
        oi.seller_id,
        o.order_id,
        oi.price,
        oi.freight_value,
        op.payment_value,
        o.order_purchase_timestamp
    FROM {{ ref('items') }} oi
    JOIN {{ ref('orders') }} o ON oi.order_id = o.order_id
    JOIN {{ ref('payments') }} op ON o.order_id = op.order_id
    WHERE o.order_status = 'delivered'
),
seller_monthly_summary AS (
    SELECT
        sr.seller_id,
        DATE_TRUNC('month', sr.order_purchase_timestamp) AS order_month,
        SUM(sr.price) AS total_sales,
        SUM(sr.freight_value) AS total_freight,
        SUM(sr.payment_value) AS total_payments
    FROM seller_revenues sr
    GROUP BY sr.seller_id, DATE_TRUNC('month', sr.order_purchase_timestamp)
),
seller_rankings AS (
    SELECT
        sms.seller_id,
        sms.order_month,
        sms.total_sales,
        sms.total_payments,
        ROW_NUMBER() OVER (
            PARTITION BY sms.order_month
            ORDER BY sms.total_sales DESC
        ) AS sales_rank
    FROM seller_monthly_summary sms
),
top_sellers AS (
    SELECT
        srk.seller_id,
        srk.order_month,
        srk.total_sales,
        srk.total_payments
    FROM seller_rankings srk
    WHERE srk.sales_rank <= 10
),
seller_review_stats AS (
    SELECT
        oi.seller_id,
        AVG(r.review_score) AS avg_review_score,
        COUNT(r.review_id) AS total_reviews
    FROM {{ ref('items') }} oi
    JOIN {{ ref('reviews') }} r ON oi.order_id = r.order_id
    GROUP BY oi.seller_id
)
SELECT
    ts.seller_id,
    ts.order_month,
    ts.total_sales AS monthly_sales,
    ts.total_payments AS monthly_payments,
    s.seller_state,
    s.seller_city,
    srs.avg_review_score,
    srs.total_reviews
FROM top_sellers ts
JOIN {{ ref('sellers') }} s ON ts.seller_id = s.seller_id
JOIN seller_review_stats srs ON ts.seller_id = srs.seller_id
ORDER BY ts.order_month DESC, ts.total_sales DESC;
