do $$
begin
  if v_mode = 'daily' then
    execute 'insert into fct_sales_daily select * from raw.sales';
  else
    execute 'insert into fct_sales_monthly select * from raw.sales';
  end if;
end $$;
