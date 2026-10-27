do $$
declare t text;
begin
  select table_name into t from meta.registry where active;
  execute 'insert into fct_registry select * from ' || t;
end $$;
