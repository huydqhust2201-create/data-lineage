CREATE TABLE stg_invoices AS (
    WITH source AS (
        SELECT * FROM raw_invoices
    )
    SELECT
        invoice_id,
        patient_id,
        department_id,
        amount_billed,
        amount_paid
    FROM source
);
