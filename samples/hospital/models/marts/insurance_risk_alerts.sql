-- File sạch (CTAS), sẽ cho ra cạnh CONFIRMED confidence 1.0 từ
-- insurance_claims_summary -- chính là "node phía sau" nằm sau 1 cạnh
-- pending mà /impact hiện KHÔNG với tới được từ phía stg_invoices.
CREATE TABLE insurance_risk_alerts AS (
    WITH source AS (
        SELECT * FROM insurance_claims_summary
    )
    SELECT
        patient_id,
        claim_status,
        CASE WHEN claim_status = 'denied' THEN TRUE ELSE FALSE END AS high_risk_claim
    FROM source
);
