{% for country in ['vn', 'us'] %}
select * from {{ source('raw', country ~ '_orders') }}
{% if not loop.last %} union all {% endif %}
{% endfor %}
