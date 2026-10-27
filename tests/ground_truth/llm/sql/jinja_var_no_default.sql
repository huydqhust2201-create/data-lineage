select * from {{ source('raw', var('table_name')) }}
