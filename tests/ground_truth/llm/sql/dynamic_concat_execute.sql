do $$
begin
  execute 'insert into fct_sales select * from ' || source_table;
end $$;
