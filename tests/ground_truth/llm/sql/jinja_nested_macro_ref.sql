{% macro pick(model_name) %}
select * from {{ ref(model_name) }}
{% endmacro %}

with a as ( {{ pick('stg_orders') }} ),
     b as ( {{ pick('stg_returns') }} )
select * from a union all select * from b
