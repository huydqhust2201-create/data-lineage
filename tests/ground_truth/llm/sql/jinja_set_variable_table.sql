{% set tbl = 'raw.orders' %}
{% set backup = 'raw.orders_backup' %}
select * from {{ tbl }}
union all
select * from {{ backup }}
