{% set offer_segments = ['gold', 'silver', 'bronze'] %}

{% for segment in offer_segments %}
SELECT
    patient_id,
    '{{ segment }}' AS segment,
    total_admissions
FROM {{ ref('patient_risk_score') }}
WHERE total_admissions {{ '>= 3' if segment == 'gold' else '>= 1' }}
{% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
