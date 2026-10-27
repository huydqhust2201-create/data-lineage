{% if target.name == 'prod' %}
select * from {{ source('raw', 'orders') }}
{% else %}
select * from {{ source('dev', 'orders') }}
{% endif %}
