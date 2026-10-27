-- Cố ý đứng GIỮA chuỗi: cạnh đi VÀO bảng này (từ stg_invoices) sẽ là pending
-- (LLM, do Jinja if/else), nhưng bảng này lại có cạnh CONFIRMED đi tiếp ra
-- insurance_risk_alerts.sql -> dùng để kiểm tra impact analysis có "đi
-- xuyên" qua 1 cạnh pending để thấy node phía sau nó hay không.
{% if var('use_partner_claims_feed', false) %}
SELECT patient_id, claim_status
FROM partner_claims_feed
{% else %}
SELECT patient_id, claim_status
FROM {{ ref('stg_invoices') }}
{% endif %}
