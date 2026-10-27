{{ config(materialized='table') }}
with orders as (select * from {{ ref('stg_orders') }}),
     customers as (select * from {{ ref('stg_customers') }}),
     payments as (select * from {{ ref('stg_payments') }})
select o.id, c.name, p.amount
from orders o
join customers c on o.customer_id = c.id
join payments p on p.order_id = o.id
