with

order_items as (

    select * from stg_order_items

),

products as (

    select * from stg_products

),

joined as (

    select
        order_items.order_id,
        products.is_food_item,
        products.is_drink_item
    from order_items
    left join products
        on order_items.product_id = products.product_id

),

aggregated as (

    select
        order_id,
        sum(
            case
                when is_food_item then 1
                else 0
            end
        ) as count_food_items,
        sum(
            case
                when is_drink_item then 1
                else 0
            end
        ) as count_drink_items
    from joined
    group by order_id

)

select * from aggregated