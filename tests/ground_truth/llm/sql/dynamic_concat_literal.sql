do $$
begin
  execute 'insert into fct_orders select * from ' || 'raw.' || 'orders';
  execute 'insert into fct_orders select * from ' || 'raw.' || 'returns';
end $$;
