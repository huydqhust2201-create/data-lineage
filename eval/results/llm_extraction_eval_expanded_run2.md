# LLM Extraction Evaluation

- Model: `openai/gpt-4.1-mini`
- Prompt version: `v1`
- SQL dialect: `postgres`
- Fixture sources: `21 cache hits, 0 live queries`
- No-hallucination fixtures are reported separately because empty expected sets do not affect micro-averages.
- Generated at: `2026-08-03T14:23:19.260846+00:00`

## Per Fixture

| Fixture | Source | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_case_when_target | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_concat_execute | cache | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('source_table', 'fct_sales')] |
| dynamic_concat_literal | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_from_column_value | cache | 0 | 3 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('fct_registry', 'dynamic_from_column_value'), ('meta.registry', 'dynamic_from_column_value'), ('t', 'dynamic_from_column_value')] |
| dynamic_multi_insert | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_opaque_function | cache | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('get_source_table(run_id)', 'dynamic_opaque_function')] |
| dynamic_table_suffix | cache | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| jinja_alias_shadows_model | cache | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/1 (0.00) | missing=[]; spurious=[] |
| jinja_for_loop_union | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_if_else_sources | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| jinja_incremental | cache | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| jinja_multi_ref_cte | cache | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/3 (0.00) | missing=[]; spurious=[] |
| jinja_nested_macro_ref | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| jinja_ref_in_loop_literal_list | cache | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/3 (0.00) | missing=[]; spurious=[] |
| jinja_ref_source | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/2 (0.50) | missing=[]; spurious=[] |
| jinja_set_variable_table | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_source_and_ref_mixed | cache | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| jinja_undefined_var | cache | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| jinja_var_no_default | cache | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| macro_definition_only | cache | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| payments_snapshot | cache | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |

## Corpus Micro-Average

Precision: 0.85; Recall: 1.00; F1: 0.92
No-hallucination fixtures: 4/7 correct (no hallucinated edges).

## Confidence Threshold Sweep

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 0.94 | 1.00 | 0.97 |
| 0.60 | 0.93 | 0.90 | 0.91 |
| 0.70 | 0.93 | 0.90 | 0.91 |
| 0.80 | 0.75 | 0.21 | 0.32 |
| 0.90 | 0.75 | 0.21 | 0.32 |
