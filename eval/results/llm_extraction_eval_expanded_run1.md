# LLM Extraction Evaluation

- Model: `openai/gpt-4.1-mini`
- Prompt version: `v1`
- SQL dialect: `postgres`
- Fixture sources: `0 cache hits, 21 live queries`
- No-hallucination fixtures are reported separately because empty expected sets do not affect micro-averages.
- Generated at: `2026-08-03T14:17:30.825158+00:00`

## Per Fixture

| Fixture | Source | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_case_when_target | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_concat_execute | live | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('source_table', 'fct_sales')] |
| dynamic_concat_literal | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_from_column_value | live | 0 | 2 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('meta.registry', 'dynamic_from_column_value'), ('t', 'fct_registry')] |
| dynamic_multi_insert | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| dynamic_opaque_function | live | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('get_source_table(run_id)', 'dynamic_opaque_function')] |
| dynamic_table_suffix | live | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| jinja_alias_shadows_model | live | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| jinja_for_loop_union | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_if_else_sources | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| jinja_incremental | live | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| jinja_multi_ref_cte | live | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/3 (0.00) | missing=[]; spurious=[] |
| jinja_nested_macro_ref | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_ref_in_loop_literal_list | live | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/3 (0.00) | missing=[]; spurious=[] |
| jinja_ref_source | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/2 (0.50) | missing=[]; spurious=[] |
| jinja_set_variable_table | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_source_and_ref_mixed | live | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 | 4/4 (1.00) | missing=[]; spurious=[] |
| jinja_undefined_var | live | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| jinja_var_no_default | live | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| macro_definition_only | live | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| payments_snapshot | live | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |

## Corpus Micro-Average

Precision: 0.88; Recall: 1.00; F1: 0.94
No-hallucination fixtures: 4/7 correct (no hallucinated edges).

## Confidence Threshold Sweep

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 0.97 | 1.00 | 0.98 |
| 0.60 | 0.96 | 0.90 | 0.93 |
| 0.70 | 0.96 | 0.90 | 0.93 |
| 0.80 | 0.86 | 0.21 | 0.33 |
| 0.90 | 0.86 | 0.21 | 0.33 |
