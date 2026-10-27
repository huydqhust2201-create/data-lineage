{{ config(materialized='table') }}
select o.id, c.name
from {{ ref('stg_orders') }} o
join {{ source('raw', 'customers') }} c on o.customer_id = c.id
