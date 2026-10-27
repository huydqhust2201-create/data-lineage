{% if var('use_beta_pricing_model', false) %}
SELECT department_id, projected_revenue
FROM beta_pricing_snapshot
{% else %}
SELECT department_id, total_revenue AS projected_revenue
FROM {{ ref('department_revenue') }}
{% endif %}
