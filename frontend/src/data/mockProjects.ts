import { LineageNodeData, LineageEdgeData, HITLQueueItem } from '../types/lineage';

export interface ProjectData {
  id: string;
  name: string;
  description: string;
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  hitlQueue: HITLQueueItem[];
}

export const mockEcommerceProject: ProjectData = {
  id: 'ecommerce-lakehouse',
  name: 'E-Commerce & Marketing Lakehouse',
  description: 'dbt Core pipeline transforming raw Shopify, Stripe & Ad platforms data into Gold Analytics Marts and Executive BI Dashboards.',
  nodes: [
    // Source Layer
    {
      id: 'raw_shopify_orders',
      name: 'raw_shopify_orders',
      schema: 'source_raw',
      layer: 'source',
      type: 'source_stream',
      description: 'Stream of raw customer orders directly ingested from Shopify Webhooks into S3 / Iceberg.',
      owner: 'Data Ingestion Team',
      tags: ['source', 'shopify', 'p0_stream'],
      freshness: '5 mins ago',
      rowCount: 1420500,
      qualityScore: 99.4,
      filePath: 'models/sources/shopify_sources.yml',
      columns: [
        { name: 'id', type: 'VARCHAR', isPrimaryKey: true, description: 'Order unique identifier' },
        { name: 'customer_id', type: 'VARCHAR', isForeignKey: true, description: 'Customer identifier' },
        { name: 'total_amount', type: 'DECIMAL(12,2)', description: 'Order gross amount' },
        { name: 'currency', type: 'VARCHAR(3)', description: 'ISO currency code' },
        { name: 'created_at', type: 'TIMESTAMP', description: 'Creation timestamp' },
        { name: 'status', type: 'VARCHAR', description: 'Order fulfillment status' }
      ]
    },
    {
      id: 'raw_stripe_payments',
      name: 'raw_stripe_payments',
      schema: 'source_raw',
      layer: 'source',
      type: 'source_stream',
      description: 'Raw Stripe payment gateway event ledger containing charge IDs, fees and refund states.',
      owner: 'FinOps Team',
      tags: ['source', 'stripe', 'finance'],
      freshness: '12 mins ago',
      rowCount: 1390200,
      qualityScore: 99.8,
      filePath: 'models/sources/stripe_sources.yml',
      columns: [
        { name: 'charge_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'order_id', type: 'VARCHAR', isForeignKey: true },
        { name: 'amount_cents', type: 'BIGINT' },
        { name: 'fee_cents', type: 'BIGINT' },
        { name: 'payment_method', type: 'VARCHAR' },
        { name: 'payment_status', type: 'VARCHAR' },
        { name: 'captured_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'raw_google_ad_spend',
      name: 'raw_google_ad_spend',
      schema: 'source_raw',
      layer: 'source',
      type: 'source_stream',
      description: 'Daily marketing spend and impression metrics from Google Ads API connector.',
      owner: 'Growth Marketing',
      tags: ['source', 'marketing', 'ads'],
      freshness: '1 hour ago',
      rowCount: 450000,
      qualityScore: 98.2,
      filePath: 'models/sources/marketing_sources.yml',
      columns: [
        { name: 'campaign_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'date', type: 'DATE' },
        { name: 'spend_usd', type: 'DECIMAL(10,2)' },
        { name: 'clicks', type: 'INT' },
        { name: 'impressions', type: 'INT' }
      ]
    },
    {
      id: 'raw_legacy_crm_logs',
      name: 'raw_legacy_crm_logs',
      schema: 'source_raw',
      layer: 'source',
      type: 'table',
      description: 'Legacy CRM database audit dump containing customer lifecycle notes with unstructured payloads.',
      owner: 'Sales Operations',
      tags: ['legacy', 'crm', 'unstructured'],
      freshness: '6 hours ago',
      rowCount: 820000,
      qualityScore: 89.1,
      isDynamicSql: true,
      filePath: 'models/sources/legacy_crm.sql',
      columns: [
        { name: 'log_id', type: 'BIGINT', isPrimaryKey: true },
        { name: 'entity_type', type: 'VARCHAR' },
        { name: 'entity_id', type: 'VARCHAR' },
        { name: 'event_payload_json', type: 'JSON' },
        { name: 'recorded_at', type: 'TIMESTAMP' }
      ]
    },

    // Staging Layer
    {
      id: 'stg_orders',
      name: 'stg_orders',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Standardized order records with cleaned timezone, normalized currencies, and deduplication logic.',
      owner: 'Data Engineering',
      tags: ['staging', 'dbt', 'orders'],
      freshness: '15 mins ago',
      rowCount: 1418000,
      qualityScore: 99.9,
      filePath: 'models/staging/stg_orders.sql',
      rawSql: `WITH source AS (
  SELECT * FROM {{ source('source_raw', 'raw_shopify_orders') }}
),
cleaned AS (
  SELECT
    id AS order_id,
    customer_id,
    CAST(total_amount AS DECIMAL(12,2)) AS order_total_usd,
    UPPER(currency) AS currency,
    LOWER(status) AS order_status,
    created_at AS order_created_at
  FROM source
  WHERE id IS NOT NULL
)
SELECT * FROM cleaned`,
      columns: [
        { name: 'order_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR', isForeignKey: true },
        { name: 'order_total_usd', type: 'DECIMAL(12,2)' },
        { name: 'currency', type: 'VARCHAR(3)' },
        { name: 'order_status', type: 'VARCHAR' },
        { name: 'order_created_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'stg_payments',
      name: 'stg_payments',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Staging table converting Stripe cents into USD dollars and classifying payment methods.',
      owner: 'Data Engineering',
      tags: ['staging', 'dbt', 'payments'],
      freshness: '15 mins ago',
      rowCount: 1390000,
      qualityScore: 100,
      filePath: 'models/staging/stg_payments.sql',
      rawSql: `WITH source AS (
  SELECT * FROM {{ source('source_raw', 'raw_stripe_payments') }}
)
SELECT
  charge_id,
  order_id,
  amount_cents / 100.0 AS payment_amount_usd,
  fee_cents / 100.0 AS payment_fee_usd,
  payment_method,
  payment_status,
  captured_at
FROM source`,
      columns: [
        { name: 'charge_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'order_id', type: 'VARCHAR', isForeignKey: true },
        { name: 'payment_amount_usd', type: 'DECIMAL(12,2)' },
        { name: 'payment_fee_usd', type: 'DECIMAL(10,2)' },
        { name: 'payment_method', type: 'VARCHAR' },
        { name: 'payment_status', type: 'VARCHAR' },
        { name: 'captured_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'stg_ad_spend',
      name: 'stg_ad_spend',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Cleaned marketing ad spend by campaign and normalized date partition.',
      owner: 'Analytics Engineering',
      tags: ['staging', 'marketing'],
      freshness: '1 hour ago',
      rowCount: 450000,
      qualityScore: 99.0,
      filePath: 'models/staging/stg_ad_spend.sql',
      columns: [
        { name: 'campaign_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'ad_date', type: 'DATE' },
        { name: 'spend_usd', type: 'DECIMAL(10,2)' },
        { name: 'clicks', type: 'INT' },
        { name: 'impressions', type: 'INT' }
      ]
    },
    {
      id: 'stg_legacy_crm_events',
      name: 'stg_legacy_crm_events',
      schema: 'staging',
      layer: 'staging',
      type: 'table',
      description: 'Parsed JSON attributes extracted from legacy CRM log entries using dynamic SQL procedures.',
      owner: 'Data Engineering',
      tags: ['staging', 'dynamic_sql', 'hitl_reviewed'],
      freshness: '6 hours ago',
      rowCount: 815000,
      qualityScore: 91.5,
      isDynamicSql: true,
      hasJinja: true,
      filePath: 'models/staging/stg_legacy_crm_events.sql',
      rawSql: `/* Dynamic SQL Unpivot & Jinja Macro Extraction */
{% set event_fields = ['churn_intent_flag', 'satisfaction_score', 'nps_rating'] %}
SELECT
  log_id,
  entity_id AS customer_id,
  {% for field in event_fields %}
    JSON_EXTRACT_SCALAR(event_payload_json, '$.{{ field }}') AS {{ field }},
  {% endfor %}
  recorded_at
FROM {{ source('source_raw', 'raw_legacy_crm_logs') }}`,
      columns: [
        { name: 'log_id', type: 'BIGINT', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR', isForeignKey: true },
        { name: 'churn_intent_flag', type: 'BOOLEAN' },
        { name: 'satisfaction_score', type: 'INT' },
        { name: 'nps_rating', type: 'INT' },
        { name: 'recorded_at', type: 'TIMESTAMP' }
      ]
    },

    // Intermediate Layer
    {
      id: 'int_orders_joined_payments',
      name: 'int_orders_joined_payments',
      schema: 'intermediate',
      layer: 'intermediate',
      type: 'materialized_view',
      description: 'Intermediate reconciliation combining order headers with verified Stripe transaction states.',
      owner: 'Analytics Engineering',
      tags: ['intermediate', 'core_logic'],
      freshness: '20 mins ago',
      rowCount: 1410000,
      qualityScore: 99.7,
      filePath: 'models/intermediate/int_orders_joined_payments.sql',
      rawSql: `SELECT
  o.order_id,
  o.customer_id,
  o.order_total_usd,
  COALESCE(p.payment_amount_usd, 0) AS actual_paid_usd,
  COALESCE(p.payment_fee_usd, 0) AS processor_fee_usd,
  o.order_status,
  p.payment_method,
  o.order_created_at
FROM {{ ref('stg_orders') }} o
LEFT JOIN {{ ref('stg_payments') }} p
  ON o.order_id = p.order_id`,
      columns: [
        { name: 'order_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR', isForeignKey: true },
        { name: 'order_total_usd', type: 'DECIMAL(12,2)' },
        { name: 'actual_paid_usd', type: 'DECIMAL(12,2)' },
        { name: 'processor_fee_usd', type: 'DECIMAL(10,2)' },
        { name: 'order_status', type: 'VARCHAR' },
        { name: 'payment_method', type: 'VARCHAR' },
        { name: 'order_created_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'int_customer_rfm_metrics',
      name: 'int_customer_rfm_metrics',
      schema: 'intermediate',
      layer: 'intermediate',
      type: 'table',
      description: 'Recency, Frequency, Monetary (RFM) calculations aggregate by customer profile.',
      owner: 'Data Science & Analytics',
      tags: ['intermediate', 'rfm', 'ml_prep'],
      freshness: '30 mins ago',
      rowCount: 295000,
      qualityScore: 99.2,
      filePath: 'models/intermediate/int_customer_rfm_metrics.sql',
      columns: [
        { name: 'customer_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'total_orders', type: 'INT' },
        { name: 'lifetime_spent_usd', type: 'DECIMAL(14,2)' },
        { name: 'first_order_date', type: 'TIMESTAMP' },
        { name: 'last_order_date', type: 'TIMESTAMP' },
        { name: 'avg_order_value_usd', type: 'DECIMAL(10,2)' }
      ]
    },

    // Marts / Gold Layer
    {
      id: 'fct_daily_sales_revenue',
      name: 'fct_daily_sales_revenue',
      schema: 'analytics_marts',
      layer: 'marts',
      type: 'table',
      description: 'Gold analytical fact table for daily executive revenue, net profit margins, and discount tracking.',
      owner: 'Lead Analytics Engineer',
      tags: ['gold', 'marts', 'p0_business'],
      freshness: '30 mins ago',
      rowCount: 1850,
      qualityScore: 100,
      filePath: 'models/marts/fct_daily_sales_revenue.sql',
      columns: [
        { name: 'sale_date', type: 'DATE', isPrimaryKey: true },
        { name: 'gross_revenue_usd', type: 'DECIMAL(14,2)' },
        { name: 'net_revenue_usd', type: 'DECIMAL(14,2)' },
        { name: 'total_transaction_fees', type: 'DECIMAL(10,2)' },
        { name: 'total_orders_count', type: 'INT' },
        { name: 'unique_purchasers', type: 'INT' }
      ]
    },
    {
      id: 'dim_customers_360',
      name: 'dim_customers_360',
      schema: 'analytics_marts',
      layer: 'marts',
      type: 'table',
      description: 'Unified customer 360 profile combining transactional history, lifetime value, and support NPS scores.',
      owner: 'Lead Analytics Engineer',
      tags: ['gold', 'dimension', 'customer_360'],
      freshness: '45 mins ago',
      rowCount: 295000,
      qualityScore: 98.9,
      filePath: 'models/marts/dim_customers_360.sql',
      columns: [
        { name: 'customer_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_tier', type: 'VARCHAR' },
        { name: 'lifetime_value_usd', type: 'DECIMAL(14,2)' },
        { name: 'rfm_segment', type: 'VARCHAR' },
        { name: 'nps_rating', type: 'INT' },
        { name: 'churn_risk_score', type: 'DECIMAL(4,3)' }
      ]
    },
    {
      id: 'fct_marketing_roi',
      name: 'fct_marketing_roi',
      schema: 'analytics_marts',
      layer: 'marts',
      type: 'table',
      description: 'Blended Customer Acquisition Cost (CAC) and Return on Ad Spend (ROAS) facts.',
      owner: 'Growth Analytics',
      tags: ['gold', 'marts', 'marketing'],
      freshness: '1 hour ago',
      rowCount: 1850,
      qualityScore: 98.4,
      filePath: 'models/marts/fct_marketing_roi.sql',
      columns: [
        { name: 'report_date', type: 'DATE', isPrimaryKey: true },
        { name: 'channel', type: 'VARCHAR' },
        { name: 'ad_spend_usd', type: 'DECIMAL(12,2)' },
        { name: 'attributed_revenue_usd', type: 'DECIMAL(12,2)' },
        { name: 'blended_roas', type: 'DECIMAL(6,2)' },
        { name: 'new_customers_acquired', type: 'INT' }
      ]
    },

    // Downstream Applications (BI, ML, Reverse ETL)
    {
      id: 'bi_executive_revenue_dashboard',
      name: 'Executive Revenue & CAC Dashboard (Tableau)',
      schema: 'bi_consumers',
      layer: 'bi_dashboard',
      type: 'dashboard',
      description: 'Critical Board of Directors & C-Level revenue metrics dashboard viewed daily.',
      owner: 'VP of Finance & Data',
      tags: ['bi', 'tableau', 'critical_c_suite'],
      freshness: 'Realtime Sync',
      rowCount: 0,
      qualityScore: 100,
      columns: [
        { name: 'metric_daily_gross_rev', type: 'KPI' },
        { name: 'metric_net_margin_pct', type: 'KPI' },
        { name: 'metric_blended_roas', type: 'KPI' }
      ]
    },
    {
      id: 'reverse_etl_hubspot_sync',
      name: 'HubSpot High-Value Customer Sync (Census/Hightouch)',
      schema: 'reverse_etl',
      layer: 'reverse_etl',
      type: 'view',
      description: 'Automated reverse ETL pipeline syncing VIP customer segments to sales team CRM.',
      owner: 'RevOps Team',
      tags: ['reverse_etl', 'hubspot', 'crm_sync'],
      freshness: 'Hourly Sync',
      rowCount: 25000,
      qualityScore: 99.5,
      columns: [
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'customer_tier', type: 'VARCHAR' },
        { name: 'lifetime_value_usd', type: 'DECIMAL(14,2)' }
      ]
    },
    {
      id: 'ml_churn_prediction_feature_store',
      name: 'Customer Churn XGBoost Feature Store (Feast)',
      schema: 'ml_platform',
      layer: 'feature_store',
      type: 'ml_feature',
      description: 'Online & offline machine learning feature table used by production churn prevention inference model.',
      owner: 'ML Engineering Team',
      tags: ['ml', 'feature_store', 'xgboost', 'production_model'],
      freshness: 'Daily Batch',
      rowCount: 295000,
      qualityScore: 97.8,
      columns: [
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'rfm_segment', type: 'VARCHAR' },
        { name: 'avg_order_value_usd', type: 'DECIMAL(10,2)' },
        { name: 'churn_risk_score', type: 'FLOAT' }
      ]
    }
  ],

  edges: [
    // Source -> Staging (Parser First: sqlglot = 1.0)
    {
      id: 'edge_raw_shopify_to_stg_orders',
      source: 'raw_shopify_orders',
      target: 'stg_orders',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Direct source() reference in stg_orders.sql parsed deterministically by sqlglot AST.',
      columnMappings: [
        { sourceCol: 'id', targetCol: 'order_id' },
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'total_amount', targetCol: 'order_total_usd' },
        { sourceCol: 'status', targetCol: 'order_status' }
      ]
    },
    {
      id: 'edge_raw_stripe_to_stg_payments',
      source: 'raw_stripe_payments',
      target: 'stg_payments',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Direct source() reference in stg_payments.sql verified by sqlglot syntax tree.',
      columnMappings: [
        { sourceCol: 'charge_id', targetCol: 'charge_id' },
        { sourceCol: 'order_id', targetCol: 'order_id' },
        { sourceCol: 'amount_cents', targetCol: 'payment_amount_usd' }
      ]
    },
    {
      id: 'edge_raw_google_ads_to_stg_ad_spend',
      source: 'raw_google_ad_spend',
      target: 'stg_ad_spend',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Standard 1-to-1 extraction verified by sqlglot AST parser.',
      columnMappings: [
        { sourceCol: 'campaign_id', targetCol: 'campaign_id' },
        { sourceCol: 'spend_usd', targetCol: 'spend_usd' }
      ]
    },

    // Source -> Staging (LLM Fallback due to dynamic SQL / Jinja)
    {
      id: 'edge_legacy_crm_to_stg_crm_events',
      source: 'raw_legacy_crm_logs',
      target: 'stg_legacy_crm_events',
      confidence: 0.94,
      inferredBy: 'gemini_llm',
      status: 'active',
      reasoning: 'Dynamic Jinja iteration `{% for field in event_fields %}` with JSON_EXTRACT_SCALAR inferred via LLM fallback analyzer.',
      columnMappings: [
        { sourceCol: 'entity_id', targetCol: 'customer_id' },
        { sourceCol: 'event_payload_json', targetCol: 'churn_intent_flag' },
        { sourceCol: 'event_payload_json', targetCol: 'nps_rating' }
      ]
    },

    // Staging -> Intermediate
    {
      id: 'edge_stg_orders_to_int_orders_payments',
      source: 'stg_orders',
      target: 'int_orders_joined_payments',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Deterministic LEFT JOIN ref("stg_orders") validated by sqlglot AST analyzer.',
      columnMappings: [
        { sourceCol: 'order_id', targetCol: 'order_id' },
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'order_total_usd', targetCol: 'total_order_amount_usd' },
        { sourceCol: 'order_status', targetCol: 'order_status' },
        { sourceCol: 'order_created_at', targetCol: 'order_created_at' }
      ]
    },
    {
      id: 'edge_stg_payments_to_int_orders_payments',
      source: 'stg_payments',
      target: 'int_orders_joined_payments',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Deterministic JOIN on order_id validated by sqlglot AST analyzer.',
      columnMappings: [
        { sourceCol: 'order_id', targetCol: 'order_id' },
        { sourceCol: 'payment_amount_usd', targetCol: 'total_paid_usd' },
        { sourceCol: 'payment_fee_usd', targetCol: 'payment_fee_usd' },
        { sourceCol: 'payment_method', targetCol: 'primary_payment_method' },
        { sourceCol: 'payment_status', targetCol: 'payment_status' }
      ]
    },
    {
      id: 'edge_stg_orders_to_int_rfm',
      source: 'stg_orders',
      target: 'int_customer_rfm_metrics',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Aggregation query `GROUP BY customer_id` parsed via sqlglot.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'order_id', targetCol: 'total_orders_count', transformType: 'COUNT()' },
        { sourceCol: 'order_total_usd', targetCol: 'lifetime_spend_usd', transformType: 'SUM()' },
        { sourceCol: 'order_total_usd', targetCol: 'average_order_value_usd', transformType: 'AVG()' },
        { sourceCol: 'order_created_at', targetCol: 'last_order_timestamp', transformType: 'MAX()' }
      ]
    },

    // Intermediate / Staging -> Marts
    {
      id: 'edge_int_orders_payments_to_fct_daily_revenue',
      source: 'int_orders_joined_payments',
      target: 'fct_daily_sales_revenue',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Direct reference in fct_daily_sales_revenue.sql parsed by sqlglot.',
      columnMappings: [
        { sourceCol: 'order_id', targetCol: 'total_orders', transformType: 'COUNT(DISTINCT)' },
        { sourceCol: 'total_order_amount_usd', targetCol: 'gross_revenue_usd', transformType: 'SUM()' },
        { sourceCol: 'payment_fee_usd', targetCol: 'net_revenue_usd', transformType: 'SUM(rev - fees)' },
        { sourceCol: 'order_created_at', targetCol: 'sales_date', transformType: 'DATE_TRUNC' }
      ]
    },
    {
      id: 'edge_int_rfm_to_dim_customers_360',
      source: 'int_customer_rfm_metrics',
      target: 'dim_customers_360',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Core customer profile join parsed by sqlglot.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'lifetime_spend_usd', targetCol: 'lifetime_spend_usd' },
        { sourceCol: 'total_orders_count', targetCol: 'total_orders' },
        { sourceCol: 'average_order_value_usd', targetCol: 'avg_order_value_usd' },
        { sourceCol: 'rfm_segment', targetCol: 'customer_tier' }
      ]
    },
    {
      id: 'edge_stg_crm_events_to_dim_customers_360',
      source: 'stg_legacy_crm_events',
      target: 'dim_customers_360',
      confidence: 0.88,
      inferredBy: 'gemini_llm',
      status: 'active',
      reasoning: 'Customer sentiment & NPS aggregation inferred by LLM model due to dynamic pivot macro.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'churn_intent_flag', targetCol: 'churn_risk_flag' },
        { sourceCol: 'nps_rating', targetCol: 'nps_score' }
      ]
    },
    {
      id: 'edge_stg_ad_spend_to_fct_marketing_roi',
      source: 'stg_ad_spend',
      target: 'fct_marketing_roi',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Marketing attribution join parsed by sqlglot.',
      columnMappings: [
        { sourceCol: 'campaign_id', targetCol: 'channel' },
        { sourceCol: 'spend_usd', targetCol: 'ad_spend_usd' },
        { sourceCol: 'spend_date', targetCol: 'report_date' }
      ]
    },
    {
      id: 'edge_fct_daily_revenue_to_fct_marketing_roi',
      source: 'fct_daily_sales_revenue',
      target: 'fct_marketing_roi',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Revenue cross-reference in blended ROAS metric.',
      columnMappings: [
        { sourceCol: 'gross_revenue_usd', targetCol: 'attributed_revenue_usd' },
        { sourceCol: 'net_revenue_usd', targetCol: 'blended_roas', transformType: 'Formula(rev/spend)' },
        { sourceCol: 'sales_date', targetCol: 'report_date' }
      ]
    },

    // Marts -> Downstream Consumers
    {
      id: 'edge_fct_daily_revenue_to_bi_exec_dashboard',
      source: 'fct_daily_sales_revenue',
      target: 'bi_executive_revenue_dashboard',
      confidence: 1.0,
      inferredBy: 'human_verified',
      status: 'active',
      reasoning: 'Tableau data source binding to fct_daily_sales_revenue.',
      columnMappings: [
        { sourceCol: 'gross_revenue_usd', targetCol: 'metric_daily_gross_rev' },
        { sourceCol: 'net_revenue_usd', targetCol: 'metric_net_margin_pct' }
      ]
    },
    {
      id: 'edge_fct_marketing_roi_to_bi_exec_dashboard',
      source: 'fct_marketing_roi',
      target: 'bi_executive_revenue_dashboard',
      confidence: 1.0,
      inferredBy: 'human_verified',
      status: 'active',
      reasoning: 'Tableau visual sheet for CAC/ROAS breakdown.',
      columnMappings: [
        { sourceCol: 'blended_roas', targetCol: 'metric_blended_roas' }
      ]
    },
    {
      id: 'edge_dim_customers_360_to_reverse_etl_hubspot',
      source: 'dim_customers_360',
      target: 'reverse_etl_hubspot_sync',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Hightouch query definition selecting VIP tiers.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'customer_tier', targetCol: 'customer_tier' },
        { sourceCol: 'lifetime_spend_usd', targetCol: 'lifetime_value_usd' }
      ]
    },
    {
      id: 'edge_dim_customers_360_to_ml_churn_feature_store',
      source: 'dim_customers_360',
      target: 'ml_churn_prediction_feature_store',
      confidence: 0.95,
      inferredBy: 'gemini_llm',
      status: 'active',
      reasoning: 'Feast feature definition referencing customer 360 profile.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'avg_order_value_usd', targetCol: 'avg_order_value_usd' },
        { sourceCol: 'churn_risk_flag', targetCol: 'churn_risk_score' }
      ]
    },
    {
      id: 'edge_int_rfm_to_ml_churn_feature_store',
      source: 'int_customer_rfm_metrics',
      target: 'ml_churn_prediction_feature_store',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active',
      reasoning: 'Direct behavioral feature ingest into Feast store.',
      columnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'rfm_segment', targetCol: 'rfm_segment' },
        { sourceCol: 'average_order_value_usd', targetCol: 'avg_order_value_usd' }
      ]
    },

    // Low confidence edge (Pending in HITL Queue)
    {
      id: 'edge_raw_shopify_to_ml_churn_suspect',
      source: 'raw_shopify_orders',
      target: 'ml_churn_prediction_feature_store',
      confidence: 0.62,
      inferredBy: 'gpt4o_mini',
      status: 'pending_hitl',
      reasoning: 'Suspected direct feature extraction from raw order JSON via experimental dynamic SQL script.'
    },
    {
      id: 'edge_raw_legacy_crm_to_fct_daily_rev_suspect',
      source: 'raw_legacy_crm_logs',
      target: 'fct_daily_sales_revenue',
      confidence: 0.58,
      inferredBy: 'gemini_llm',
      status: 'pending_hitl',
      reasoning: 'Detected string concatenation SQL querying legacy audit log inside revenue adjustment stored procedure.'
    }
  ],

  hitlQueue: [
    {
      id: 'hitl_001',
      edgeId: 'edge_raw_shopify_to_ml_churn_suspect',
      sourceTable: 'raw_shopify_orders',
      targetTable: 'ml_churn_prediction_feature_store',
      sourceSchema: 'source_raw',
      targetSchema: 'ml_platform',
      confidence: 0.62,
      inferredBy: 'gpt4o_mini',
      detectedIssue: 'dynamic_sql',
      reason: 'SQL uses string concatenation inside a Python UDF to dynamically query `raw_shopify_orders` without dbt ref() macro.',
      sqlSnippet: `def get_recent_cart_abandons(customer_id):
    query = f"SELECT COUNT(*) FROM source_raw.raw_shopify_orders WHERE customer_id = '{customer_id}' AND status = 'abandoned'"
    return spark.sql(query).collect()[0][0]`,
      filePath: 'pipelines/ml/feature_extraction_udf.py',
      suggestedColumnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' },
        { sourceCol: 'status', targetCol: 'churn_risk_score' }
      ],
      status: 'pending',
      timestamp: '2026-08-15 11:45:00'
    },
    {
      id: 'hitl_002',
      edgeId: 'edge_raw_legacy_crm_to_fct_daily_rev_suspect',
      sourceTable: 'raw_legacy_crm_logs',
      targetTable: 'fct_daily_sales_revenue',
      sourceSchema: 'source_raw',
      targetSchema: 'analytics_marts',
      confidence: 0.58,
      inferredBy: 'gemini_llm',
      detectedIssue: 'string_concatenation',
      reason: 'Stored procedure `sp_reconcile_disputes` executes dynamic SQL string building against legacy audit logs.',
      sqlSnippet: `SET @sql = CONCAT('SELECT SUM(JSON_EXTRACT(event_payload_json, "$.dispute_amt")) FROM source_raw.raw_legacy_crm_logs WHERE entity_type = "DISPUTE"');
PREPARE stmt FROM @sql;
EXECUTE stmt;`,
      filePath: 'procedures/sp_reconcile_disputes.sql',
      suggestedColumnMappings: [
        { sourceCol: 'event_payload_json', targetCol: 'net_revenue_usd' }
      ],
      status: 'pending',
      timestamp: '2026-08-15 11:52:30'
    },
    {
      id: 'hitl_003',
      edgeId: 'edge_unresolved_jinja_macro_attribution',
      sourceTable: 'raw_google_ad_spend',
      targetTable: 'int_customer_rfm_metrics',
      sourceSchema: 'source_raw',
      targetSchema: 'intermediate',
      confidence: 0.69,
      inferredBy: 'gemini_llm',
      detectedIssue: 'jinja_macro',
      reason: 'Uncompiled Jinja macro `{{ generate_campaign_weighting(source("source_raw", "raw_google_ad_spend")) }}` lacks compiled target resolution.',
      sqlSnippet: `{{ config(materialized='table') }}
SELECT
  c.customer_id,
  {{ generate_campaign_weighting(source('source_raw', 'raw_google_ad_spend')) }} as ad_touch_score
FROM {{ ref('stg_orders') }} c`,
      filePath: 'models/intermediate/int_customer_rfm_metrics.sql',
      suggestedColumnMappings: [
        { sourceCol: 'campaign_id', targetCol: 'customer_id' }
      ],
      status: 'pending',
      timestamp: '2026-08-15 12:00:10'
    }
  ]
};

export const mockRetailOmniProject: ProjectData = {
  id: 'retail-omni-channel',
  name: 'Retail Omni-Channel Analytics',
  description: 'Tích hợp dữ liệu giao dịch Web/App, máy POS tại cửa hàng, thẻ thành viên loyalty, logistics kho vận và Dashboard báo cáo doanh số đa kênh.',
  nodes: [
    {
      id: 'raw_shopify_sales',
      name: 'raw_shopify_sales',
      schema: 'source_raw',
      layer: 'source',
      type: 'source_stream',
      description: 'Stream of raw Shopify orders ingested from Webhooks.',
      owner: 'E-Commerce Platform Team',
      tags: ['shopify', 'ecom', 'stream'],
      columns: [
        { name: 'id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'total_amount', type: 'DECIMAL(12,2)' },
        { name: 'currency', type: 'VARCHAR' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'status', type: 'VARCHAR' }
      ]
    },
    {
      id: 'raw_pos_transactions',
      name: 'raw_pos_transactions',
      schema: 'source_raw',
      layer: 'source',
      type: 'table',
      description: 'In-store point of sale physical register transactions.',
      owner: 'Retail IT Team',
      tags: ['pos', 'retail', 'batch'],
      columns: [
        { name: 'transaction_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'store_id', type: 'VARCHAR' },
        { name: 'register_id', type: 'VARCHAR' },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'amount', type: 'DECIMAL(10,2)' },
        { name: 'timestamp', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'raw_loyalty_customers',
      name: 'raw_loyalty_customers',
      schema: 'source_raw',
      layer: 'source',
      type: 'table',
      description: 'Customer CRM database for loyalty cards and member details.',
      owner: 'Marketing Ops',
      tags: ['crm', 'loyalty'],
      columns: [
        { name: 'loyalty_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'email', type: 'VARCHAR' },
        { name: 'joined_date', type: 'TIMESTAMP' },
        { name: 'tier', type: 'VARCHAR' },
        { name: 'points', type: 'INT' }
      ]
    },
    {
      id: 'raw_inventory_logs',
      name: 'raw_inventory_logs',
      schema: 'source_raw',
      layer: 'source',
      type: 'source_stream',
      description: 'IoT warehousing logs tracking item stock levels.',
      owner: 'Logistics Team',
      tags: ['iot', 'inventory'],
      columns: [
        { name: 'log_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'sku', type: 'VARCHAR' },
        { name: 'warehouse_id', type: 'VARCHAR' },
        { name: 'quantity', type: 'INT' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'raw_feedback_csv',
      name: 'raw_feedback_csv',
      schema: 'source_raw',
      layer: 'source',
      type: 'table',
      description: 'S3 storage for customer feedback survey CSVs.',
      owner: 'Customer Experience',
      tags: ['s3', 'feedback'],
      columns: [
        { name: 'feedback_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_email', type: 'VARCHAR' },
        { name: 'rating', type: 'INT' },
        { name: 'comments', type: 'VARCHAR' },
        { name: 'date', type: 'DATE' }
      ]
    },
    {
      id: 'stg_shopify_orders',
      name: 'stg_shopify_orders',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Normalized Shopify web sales order attributes.',
      owner: 'Analytics Engineering',
      tags: ['staging'],
      columns: [
        { name: 'order_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'order_total_usd', type: 'DECIMAL(12,2)' },
        { name: 'order_status', type: 'VARCHAR' },
        { name: 'order_date', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'stg_pos_sales',
      name: 'stg_pos_sales',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Normalized POS physical store transaction entries.',
      owner: 'Analytics Engineering',
      tags: ['staging'],
      columns: [
        { name: 'sale_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'store_id', type: 'VARCHAR' },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'sale_amount_usd', type: 'DECIMAL(10,2)' },
        { name: 'sale_date', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'stg_loyalty_profiles',
      name: 'stg_loyalty_profiles',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Standardized customer loyalty memberships.',
      owner: 'Marketing Analytics',
      tags: ['staging'],
      columns: [
        { name: 'loyalty_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'email_address', type: 'VARCHAR' },
        { name: 'loyalty_tier', type: 'VARCHAR' },
        { name: 'points_balance', type: 'INT' }
      ]
    },
    {
      id: 'stg_inventory_levels',
      name: 'stg_inventory_levels',
      schema: 'staging',
      layer: 'staging',
      type: 'view',
      description: 'Hourly inventory snapshots.',
      owner: 'Logistics Analytics',
      tags: ['staging'],
      columns: [
        { name: 'snapshot_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'product_sku', type: 'VARCHAR' },
        { name: 'warehouse_id', type: 'VARCHAR' },
        { name: 'stock_level', type: 'INT' },
        { name: 'recorded_at', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'int_omnichannel_sales',
      name: 'int_omnichannel_sales',
      schema: 'intermediate',
      layer: 'intermediate',
      type: 'table',
      description: 'Unified transactions merging shopify and POS sales.',
      owner: 'Analytics Engineering',
      tags: ['intermediate'],
      columns: [
        { name: 'sale_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'amount_usd', type: 'DECIMAL(12,2)' },
        { name: 'sales_channel', type: 'VARCHAR' },
        { name: 'sales_date', type: 'TIMESTAMP' }
      ]
    },
    {
      id: 'int_customer_loyalty_spend',
      name: 'int_customer_loyalty_spend',
      schema: 'intermediate',
      layer: 'intermediate',
      type: 'table',
      description: 'Enriched transactions linked with loyalty profiles.',
      owner: 'Marketing Analytics',
      tags: ['intermediate'],
      columns: [
        { name: 'customer_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'loyalty_id', type: 'VARCHAR' },
        { name: 'total_spend_usd', type: 'DECIMAL(12,2)' },
        { name: 'points_accumulated', type: 'INT' },
        { name: 'tier', type: 'VARCHAR' }
      ]
    },
    {
      id: 'int_inventory_replenish',
      name: 'int_inventory_replenish',
      schema: 'intermediate',
      layer: 'intermediate',
      type: 'table',
      description: 'Calculates inventory replenishment velocity and stock requirements.',
      owner: 'Logistics Analytics',
      tags: ['intermediate'],
      columns: [
        { name: 'product_sku', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'stock_level', type: 'INT' },
        { name: 'avg_daily_sales', type: 'DECIMAL(10,2)' },
        { name: 'days_of_stock', type: 'INT' },
        { name: 'reorder_needed', type: 'VARCHAR' }
      ]
    },
    {
      id: 'fct_daily_store_revenue',
      name: 'fct_daily_store_revenue',
      schema: 'analytics_gold',
      layer: 'marts',
      type: 'table',
      description: 'Gold table of consolidated revenue metrics.',
      owner: 'Lead Analyst',
      tags: ['marts', 'revenue', 'gold'],
      columns: [
        { name: 'sales_date', type: 'DATE', isPrimaryKey: true },
        { name: 'online_sales_usd', type: 'DECIMAL(12,2)' },
        { name: 'retail_sales_usd', type: 'DECIMAL(12,2)' },
        { name: 'total_sales_usd', type: 'DECIMAL(12,2)' }
      ]
    },
    {
      id: 'dim_loyalty_members_360',
      name: 'dim_loyalty_members_360',
      schema: 'analytics_gold',
      layer: 'marts',
      type: 'table',
      description: 'Complete profile of loyalty members and buying habits.',
      owner: 'Lead Analyst',
      tags: ['marts', 'customers', 'gold'],
      columns: [
        { name: 'loyalty_id', type: 'VARCHAR', isPrimaryKey: true },
        { name: 'customer_id', type: 'VARCHAR' },
        { name: 'total_orders', type: 'INT' },
        { name: 'total_spend_usd', type: 'DECIMAL(12,2)' },
        { name: 'loyalty_tier', type: 'VARCHAR' },
        { name: 'points_balance', type: 'INT' }
      ]
    },
    {
      id: 'bi_omnichannel_sales_dashboard',
      name: 'Executive Omnichannel Sales Dashboard',
      schema: 'bi_dashboard',
      layer: 'bi_dashboard',
      type: 'dashboard',
      description: 'Executive dashboard for omnichannel sales.',
      owner: 'VP of Retail',
      tags: ['bi', 'dashboard', 'tableau'],
      columns: [
        { name: 'kpi_total_sales', type: 'DECIMAL' },
        { name: 'kpi_loyalty_revenue_share', type: 'DECIMAL' },
        { name: 'kpi_low_stock_alerts', type: 'INT' }
      ]
    }
  ],

  edges: [
    {
      id: 'edge_raw_shopify_to_stg_shopify',
      source: 'raw_shopify_sales',
      target: 'stg_shopify_orders',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_raw_pos_to_stg_pos',
      source: 'raw_pos_transactions',
      target: 'stg_pos_sales',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_raw_loyalty_to_stg_loyalty',
      source: 'raw_loyalty_customers',
      target: 'stg_loyalty_profiles',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_raw_inventory_to_stg_inventory',
      source: 'raw_inventory_logs',
      target: 'stg_inventory_levels',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_stg_shopify_to_int_sales',
      source: 'stg_shopify_orders',
      target: 'int_omnichannel_sales',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_stg_pos_to_int_sales',
      source: 'stg_pos_sales',
      target: 'int_omnichannel_sales',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_stg_loyalty_to_int_loyalty',
      source: 'stg_loyalty_profiles',
      target: 'int_customer_loyalty_spend',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_int_sales_to_int_loyalty',
      source: 'int_omnichannel_sales',
      target: 'int_customer_loyalty_spend',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_stg_inventory_to_int_replenish',
      source: 'stg_inventory_levels',
      target: 'int_inventory_replenish',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_int_sales_to_fct_revenue',
      source: 'int_omnichannel_sales',
      target: 'fct_daily_store_revenue',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_int_loyalty_to_dim_members',
      source: 'int_customer_loyalty_spend',
      target: 'dim_loyalty_members_360',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_int_replenish_to_bi_dashboard',
      source: 'int_inventory_replenish',
      target: 'bi_omnichannel_sales_dashboard',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_fct_revenue_to_bi_dashboard',
      source: 'fct_daily_store_revenue',
      target: 'bi_omnichannel_sales_dashboard',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_dim_members_to_bi_dashboard',
      source: 'dim_loyalty_members_360',
      target: 'bi_omnichannel_sales_dashboard',
      confidence: 1.0,
      inferredBy: 'sqlglot_parser',
      status: 'active'
    },
    {
      id: 'edge_raw_feedback_to_loyalty_suspect',
      source: 'raw_feedback_csv',
      target: 'stg_loyalty_profiles',
      confidence: 0.64,
      inferredBy: 'gemini_llm',
      status: 'pending_hitl',
      reasoning: 'Dynamic file reading and string concatenation of feedback CSV files parsed via pandas.'
    },
    {
      id: 'edge_raw_shopify_to_replenish_suspect',
      source: 'raw_shopify_sales',
      target: 'int_inventory_replenish',
      confidence: 0.52,
      inferredBy: 'gpt4o_mini',
      status: 'pending_hitl',
      reasoning: 'Dynamic partition SQL query loading Shopify daily sales into logistics warehouse.'
    },
    {
      id: 'edge_pos_to_customer_loyalty_suspect',
      source: 'raw_pos_transactions',
      target: 'int_customer_loyalty_spend',
      confidence: 0.69,
      inferredBy: 'gemini_llm',
      status: 'pending_hitl',
      reasoning: 'Query references unqualified fields points and total_amount in a nested subquery that joins loyalty accounts.'
    },
    {
      id: 'edge_shopify_orders_to_revenue_suspect',
      source: 'stg_shopify_orders',
      target: 'fct_daily_store_revenue',
      confidence: 0.55,
      inferredBy: 'gpt4o_mini',
      status: 'pending_hitl',
      reasoning: 'Uncompiled Jinja macro {{ get_low_stock_threshold() }} used to evaluate stock levels.'
    },
    {
      id: 'edge_loyalty_to_dashboard_suspect',
      source: 'dim_loyalty_members_360',
      target: 'bi_omnichannel_sales_dashboard',
      confidence: 0.72,
      inferredBy: 'gemini_llm',
      status: 'pending_hitl',
      reasoning: 'Dynamic Salesforce Bulk API insert targeting columns fetched from runtime metadata table.'
    }
  ],
  hitlQueue: [
    {
      id: 'hitl_rt_001',
      edgeId: 'edge_raw_feedback_to_loyalty_suspect',
      sourceTable: 'raw_feedback_csv',
      targetTable: 'stg_loyalty_profiles',
      sourceSchema: 'source_raw',
      targetSchema: 'staging',
      confidence: 0.64,
      inferredBy: 'gemini_llm',
      detectedIssue: 'string_concatenation',
      reason: 'Dynamic file reading and string concatenation of feedback CSV files parsed via pandas.',
      sqlSnippet: "df = pd.read_csv('s3://feedback/' + date_str + '_customer_feedback.csv')",
      filePath: 'pipelines/ingest_feedback.py',
      suggestedColumnMappings: [
        { sourceCol: 'customer_email', targetCol: 'email_address' }
      ],
      status: 'pending',
      timestamp: '2026-08-20 14:10:00'
    },
    {
      id: 'hitl_rt_002',
      edgeId: 'edge_raw_shopify_to_replenish_suspect',
      sourceTable: 'raw_shopify_sales',
      targetTable: 'int_inventory_replenish',
      sourceSchema: 'source_raw',
      targetSchema: 'intermediate',
      confidence: 0.52,
      inferredBy: 'gpt4o_mini',
      detectedIssue: 'dynamic_sql',
      reason: 'Dynamic partition SQL query loading Shopify daily sales into logistics warehouse.',
      sqlSnippet: "spark.sql(f\"SELECT sku, SUM(quantity) FROM omnichannel.raw_shopify_sales WHERE order_date = '{partition_date}' GROUP BY sku\")",
      filePath: 'jobs/inventory_replenish_sync.py',
      suggestedColumnMappings: [
        { sourceCol: 'sku', targetCol: 'product_sku' }
      ],
      status: 'pending',
      timestamp: '2026-08-20 14:15:00'
    },
    {
      id: 'hitl_rt_003',
      edgeId: 'edge_pos_to_customer_loyalty_suspect',
      sourceTable: 'raw_pos_transactions',
      targetTable: 'int_customer_loyalty_spend',
      sourceSchema: 'source_raw',
      targetSchema: 'intermediate',
      confidence: 0.69,
      inferredBy: 'gemini_llm',
      detectedIssue: 'ambiguous_alias',
      reason: 'Query references unqualified fields points and total_amount in a nested subquery that joins loyalty accounts.',
      sqlSnippet: 'SELECT customer_id, SUM(points) FROM source_raw.raw_pos_transactions JOIN loyalty_members USING (customer_id)',
      filePath: 'models/intermediate/int_customer_loyalty_spend.sql',
      suggestedColumnMappings: [
        { sourceCol: 'customer_id', targetCol: 'customer_id' }
      ],
      status: 'pending',
      timestamp: '2026-08-20 14:20:00'
    },
    {
      id: 'hitl_rt_004',
      edgeId: 'edge_shopify_orders_to_revenue_suspect',
      sourceTable: 'stg_shopify_orders',
      targetTable: 'fct_daily_store_revenue',
      sourceSchema: 'staging',
      targetSchema: 'analytics_gold',
      confidence: 0.55,
      inferredBy: 'gpt4o_mini',
      detectedIssue: 'jinja_macro',
      reason: 'Uncompiled Jinja macro {{ get_low_stock_threshold() }} used to evaluate stock levels.',
      sqlSnippet: 'SELECT item_sku, current_stock FROM {{ ref(\'stg_shopify_orders\') }} WHERE current_stock < {{ get_low_stock_threshold() }}',
      filePath: 'models/marts/fct_daily_store_revenue.sql',
      suggestedColumnMappings: [
        { sourceCol: 'item_sku', targetCol: 'total_sales_usd' }
      ],
      status: 'pending',
      timestamp: '2026-08-20 14:25:00'
    },
    {
      id: 'hitl_rt_005',
      edgeId: 'edge_loyalty_to_dashboard_suspect',
      sourceTable: 'dim_loyalty_members_360',
      targetTable: 'bi_omnichannel_sales_dashboard',
      sourceSchema: 'analytics_gold',
      targetSchema: 'bi_dashboard',
      confidence: 0.72,
      inferredBy: 'gemini_llm',
      detectedIssue: 'dynamic_sql',
      reason: 'Dynamic Salesforce Bulk API insert targeting columns fetched from runtime metadata table.',
      sqlSnippet: 'sf_columns = [col[0] for col in db.execute("SELECT col_name FROM meta.sf_mapping")]',
      filePath: 'integrations/reverse_etl_salesforce.py',
      suggestedColumnMappings: [
        { sourceCol: 'loyalty_id', targetCol: 'kpi_loyalty_revenue_share' }
      ],
      status: 'pending',
      timestamp: '2026-08-20 14:30:00'
    }
  ]
};



export const mockProjectsList: ProjectData[] = [
  mockEcommerceProject,
  {
    id: 'finance-ops-dw',
    name: 'Finance & Operations DW',
    description: 'Modern analytical warehouse consolidating ERP invoices, operational expense ledger, currency rates, and cash flow projections.',
    nodes: [
      {
        id: 'raw_erp_invoices',
        name: 'raw_erp_invoices',
        schema: 'erp_raw',
        layer: 'source',
        type: 'source_stream',
        description: 'Raw customer invoices generated by the operational ERP platform.',
        owner: 'ERP Platform Team',
        tags: ['erp', 'billing', 'raw'],
        freshness: '10 mins ago',
        rowCount: 850000,
        qualityScore: 99.1,
        filePath: 'models/sources/erp_sources.yml',
        columns: [
          { name: 'invoice_id', type: 'VARCHAR', isPrimaryKey: true, description: 'Unique invoice code' },
          { name: 'customer_id', type: 'VARCHAR', isForeignKey: true, description: 'Reference to customer master' },
          { name: 'gross_amount_usd', type: 'DECIMAL(12,2)', description: 'Total charge amount before tax' },
          { name: 'tax_amount_usd', type: 'DECIMAL(12,2)', description: 'Calculated tax amount' },
          { name: 'status', type: 'VARCHAR', description: 'Payment status (unpaid, paid, voided)' },
          { name: 'created_at', type: 'TIMESTAMP', description: 'Invoice creation date' }
        ]
      },
      {
        id: 'raw_opex_ledger',
        name: 'raw_opex_ledger',
        schema: 'finance_raw',
        layer: 'source',
        type: 'table',
        description: 'Ledger tracking corporate operational expenditure and vendor invoices.',
        owner: 'FinOps Team',
        tags: ['opex', 'ledger', 'critical'],
        freshness: '1 hour ago',
        rowCount: 120000,
        qualityScore: 99.8,
        filePath: 'models/sources/finance_sources.yml',
        columns: [
          { name: 'entry_id', type: 'VARCHAR', isPrimaryKey: true, description: 'Ledger entry UUID' },
          { name: 'vendor_id', type: 'VARCHAR', description: 'Vendor code' },
          { name: 'category', type: 'VARCHAR', description: 'Expense category (SaaS, Marketing, Rent, Travel)' },
          { name: 'amount_usd', type: 'DECIMAL(12,2)', description: 'Transaction amount in USD' },
          { name: 'logged_at', type: 'TIMESTAMP', description: 'Timestamp when logged' }
        ]
      },
      {
        id: 'stg_erp_invoices',
        name: 'stg_erp_invoices',
        schema: 'staging',
        layer: 'staging',
        type: 'view',
        description: 'Cleaned and validated ERP invoices with normalized status states.',
        owner: 'Financial Analytics',
        tags: ['staging', 'normalized'],
        freshness: '12 mins ago',
        rowCount: 850000,
        qualityScore: 99.5,
        filePath: 'models/staging/stg_erp_invoices.sql',
        columns: [
          { name: 'invoice_id', type: 'VARCHAR', isPrimaryKey: true, description: 'Unique invoice identifier' },
          { name: 'customer_id', type: 'VARCHAR', description: 'Normalized customer identifier' },
          { name: 'amount_usd', type: 'DECIMAL(12,2)', description: 'Normalized gross amount' },
          { name: 'is_settled', type: 'BOOLEAN', description: 'True if status is paid' },
          { name: 'issued_date', type: 'DATE', description: 'Date portion of creation' }
        ]
      },
      {
        id: 'fct_corporate_cash_flow',
        name: 'fct_corporate_cash_flow',
        schema: 'analytics_marts',
        layer: 'marts',
        type: 'table',
        description: 'Daily cash inflow and outflow facts aggregated by department and business unit.',
        owner: 'Treasury Team',
        tags: ['marts', 'cash_flow', 'gold'],
        freshness: '4 hours ago',
        rowCount: 45000,
        qualityScore: 99.9,
        filePath: 'models/marts/fct_corporate_cash_flow.sql',
        columns: [
          { name: 'record_date', type: 'DATE', isPrimaryKey: true, description: 'Reporting day' },
          { name: 'total_inflow_usd', type: 'DECIMAL(15,2)', description: 'Sum of paid invoices volume' },
          { name: 'total_outflow_usd', type: 'DECIMAL(15,2)', description: 'Sum of opex vendor payouts' },
          { name: 'net_cash_flow_usd', type: 'DECIMAL(15,2)', description: 'Net treasury change (inflow - outflow)' }
        ]
      },
      {
        id: 'bi_cfo_liquidity_dashboard',
        name: 'CFO Liquidity & Burn-Rate Dashboard',
        schema: 'compliance',
        layer: 'bi_dashboard',
        type: 'dashboard',
        description: 'Executive dashboard tracking burn-rate, runway, and cash balance for C-Suite alignment.',
        owner: 'Finance Director',
        tags: ['bi', 'cfo', 'runway', 'critical'],
        freshness: 'Live updates',
        rowCount: 1,
        qualityScore: 100.0,
        filePath: 'dashboards/cfo_liquidity.json',
        columns: [
          { name: 'current_cash_reserve', type: 'DECIMAL(18,2)', description: 'Total treasury bank balance' },
          { name: 'average_monthly_burn', type: 'DECIMAL(12,2)', description: '3-month rolling opex average' },
          { name: 'projected_runway_months', type: 'DECIMAL(4,1)', description: 'Months of survival under current burn-rate' }
        ]
      }
    ],
    edges: [
      {
        id: 'edge_raw_erp_to_stg',
        source: 'raw_erp_invoices',
        target: 'stg_erp_invoices',
        confidence: 1.0,
        inferredBy: 'sqlglot_parser',
        status: 'active'
      },
      {
        id: 'edge_stg_to_cash_flow',
        source: 'stg_erp_invoices',
        target: 'fct_corporate_cash_flow',
        confidence: 1.0,
        inferredBy: 'sqlglot_parser',
        status: 'active'
      },
      {
        id: 'edge_opex_to_cash_flow',
        source: 'raw_opex_ledger',
        target: 'fct_corporate_cash_flow',
        confidence: 1.0,
        inferredBy: 'sqlglot_parser',
        status: 'active'
      },
      {
        id: 'edge_cash_flow_to_bi',
        source: 'fct_corporate_cash_flow',
        target: 'bi_cfo_liquidity_dashboard',
        confidence: 1.0,
        inferredBy: 'human_verified',
        status: 'active'
      }
    ],
    hitlQueue: []
  },
  {
    id: 'fintech-fraud-ledger',
    name: 'FinTech Core Ledger & Fraud Graph',
    description: 'Real-time card transactions, ISO 20022 clearing, ML fraud scoring & Central Bank regulatory filings.',
    nodes: [
      {
        id: 'raw_card_swipes',
        name: 'raw_card_swipes',
        schema: 'core_banking',
        layer: 'source',
        type: 'source_stream',
        description: 'Kafka stream of POS & Online EMV 3DS transactions.',
        owner: 'Switch Team',
        tags: ['fintech', 'pci_dss', 'p0'],
        columns: [
          { name: 'pan_token', type: 'VARCHAR', isPrimaryKey: true },
          { name: 'amount_usd', type: 'DECIMAL(12,2)' },
          { name: 'merchant_mcc', type: 'VARCHAR(4)' },
          { name: 'timestamp', type: 'TIMESTAMP' }
        ]
      },
      {
        id: 'stg_card_transactions',
        name: 'stg_card_transactions',
        schema: 'staging',
        layer: 'staging',
        type: 'view',
        description: 'Normalized ledger debit/credit entries with ISO currency conversion.',
        owner: 'FinData Team',
        tags: ['staging'],
        columns: [
          { name: 'txn_id', type: 'VARCHAR', isPrimaryKey: true },
          { name: 'pan_token', type: 'VARCHAR' },
          { name: 'amount_usd', type: 'DECIMAL(12,2)' },
          { name: 'status', type: 'VARCHAR' }
        ]
      },
      {
        id: 'fct_fraud_risk_scores',
        name: 'fct_fraud_risk_scores',
        schema: 'analytics_marts',
        layer: 'marts',
        type: 'table',
        description: 'Real-time and batch fraud probability scoring model table.',
        owner: 'Risk AI Team',
        tags: ['fraud', 'risk', 'gold'],
        columns: [
          { name: 'txn_id', type: 'VARCHAR', isPrimaryKey: true },
          { name: 'fraud_score', type: 'FLOAT' },
          { name: 'decision', type: 'VARCHAR' }
        ]
      },
      {
        id: 'bi_regulatory_anti_money_laundering_report',
        name: 'Anti-Money Laundering (AML) Compliance Dashboard',
        schema: 'compliance',
        layer: 'bi_dashboard',
        type: 'dashboard',
        description: 'Mandatory daily SAR/AML regulatory filings for Central Bank auditing.',
        owner: 'Compliance Officer',
        tags: ['regulatory', 'compliance', 'critical'],
        columns: [
          { name: 'suspicious_txn_count', type: 'INT' },
          { name: 'total_flagged_volume_usd', type: 'DECIMAL(14,2)' }
        ]
      }
    ],
    edges: [
      {
        id: 'edge_swipes_to_stg',
        source: 'raw_card_swipes',
        target: 'stg_card_transactions',
        confidence: 1.0,
        inferredBy: 'sqlglot_parser',
        status: 'active'
      },
      {
        id: 'edge_stg_to_fraud',
        source: 'stg_card_transactions',
        target: 'fct_fraud_risk_scores',
        confidence: 1.0,
        inferredBy: 'sqlglot_parser',
        status: 'active'
      },
      {
        id: 'edge_fraud_to_bi',
        source: 'fct_fraud_risk_scores',
        target: 'bi_regulatory_anti_money_laundering_report',
        confidence: 1.0,
        inferredBy: 'human_verified',
        status: 'active'
      }
    ],
    hitlQueue: []
  },
  mockRetailOmniProject
];
