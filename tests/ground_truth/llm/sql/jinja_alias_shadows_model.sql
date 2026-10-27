select stg_orders.id
from {{ ref('stg_payments') }} as stg_orders
