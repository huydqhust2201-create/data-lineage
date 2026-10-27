{% set models = ['stg_orders', 'stg_returns', 'stg_refunds'] %}
{% for m in models %}
select * from {{ ref(m) }}
{% if not loop.last %} union all {% endif %}
{% endfor %}
