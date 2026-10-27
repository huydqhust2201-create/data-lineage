execute 'insert into fct_events select * from ' || get_source_table(run_id);
