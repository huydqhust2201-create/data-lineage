with compute_booleans as (

    select * from stg_orders

),

customer_order_count as (

    select
        customer_id,
        ordered_at,
        row_number() over (
            partition by customer_id
            order by ordered_at asc
        ) as customer_order_number
    from compute_booleans

)

select * from customer_order_count