do $$
begin
  execute 'insert into fct_orders select * from raw.orders';
  execute 'insert into fct_customers select * from raw.customers';
end $$;
