execute 'create table daily_sales_' || run_date || ' as select * from raw.orders';
