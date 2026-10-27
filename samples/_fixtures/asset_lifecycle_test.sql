-- Fixture lifecycle cho get_asset / chatbot, không phải Hospital model.
-- Kịch bản lỗi: asset_lifecycle_revenue_report vẫn phụ thuộc vào source đã
-- đổi tên. Chat cần trace upstream tới asset_lifecycle_invoice_source_v2,
-- rồi get_asset phải cho biết tên cũ là asset_lifecycle_legacy_invoice_source.
-- Có thêm bảng bị drop để test is_dropped.

CREATE TABLE asset_lifecycle_legacy_invoice_source AS
SELECT
    department_id,
    amount_paid
FROM stg_invoices;

CREATE TABLE asset_lifecycle_revenue_report AS
SELECT
    department_id,
    SUM(amount_paid) AS total_revenue
FROM asset_lifecycle_legacy_invoice_source
GROUP BY department_id;

ALTER TABLE asset_lifecycle_legacy_invoice_source
RENAME TO asset_lifecycle_invoice_source_v2;

CREATE TABLE asset_lifecycle_retired_snapshot AS
SELECT
    invoice_id,
    amount_paid
FROM stg_invoices;

DROP TABLE asset_lifecycle_retired_snapshot;
