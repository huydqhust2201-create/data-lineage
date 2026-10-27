with

orders_web as (

    select
        order_id,
        customer_id,
        order_date,
        status,
        amount,
        'web' as order_source
    from stg_orders
    where status != 'returned'

),

orders_app as (

    select
        order_id,
        customer_id,
        order_date,
        status,
        amount,
        'app' as order_source
    from stg_orders_app
    where status != 'returned'

),

all_orders as (

    select * from orders_web

    union all

    select * from orders_app

)

select * from all_orders