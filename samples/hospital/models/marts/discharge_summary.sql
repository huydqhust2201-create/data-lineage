{% if var('use_legacy_admissions', false) %}
SELECT patient_id, ward, discharged_at
FROM legacy_admissions
WHERE discharged_at IS NOT NULL
{% else %}
SELECT patient_id, ward, discharged_at
FROM {{ ref('stg_admissions') }}
WHERE discharged_at IS NOT NULL
{% endif %}
