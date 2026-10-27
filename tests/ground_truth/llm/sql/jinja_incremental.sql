select * from {{ ref('stg_orders') }}
{% if is_incremental() %}
where id > (select max(id) from {{ this }})
{% endif %}
