select * from {{ source('raw', 'orders') }}
union all
select * from {{ source('raw', 'orders_archive') }}
union all
select * from {{ ref('stg_orders_manual') }}
union all
select * from {{ ref('stg_orders_legacy') }}
