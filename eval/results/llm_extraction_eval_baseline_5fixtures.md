# LLM Extraction Evaluation

- Model: `openai/gpt-4.1-mini`
- Prompt version: `v1`
- SQL dialect: `postgres`
- Fixture sources: `5 cache hits, 0 live queries`
- No-hallucination fixtures are reported separately because empty expected sets do not affect micro-averages.
- Generated at: `2026-08-03T14:12:12.153270+00:00`

## Per Fixture

| Fixture | Source | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_concat_execute | cache | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('source_table', 'fct_sales')] |
| dynamic_table_suffix | cache | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| jinja_for_loop_union | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0/2 (0.00) | missing=[]; spurious=[] |
| jinja_incremental | cache | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| jinja_ref_source | cache | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/2 (0.50) | missing=[]; spurious=[] |

## Corpus Micro-Average

Precision: 0.83; Recall: 1.00; F1: 0.91
No-hallucination fixtures: 1/2 correct (no hallucinated edges).

## Confidence Threshold Sweep

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 1.00 | 1.00 | 1.00 |
| 0.60 | 1.00 | 1.00 | 1.00 |
| 0.70 | 1.00 | 1.00 | 1.00 |
| 0.80 | 0.00 | 0.00 | 0.00 |
| 0.90 | 0.00 | 0.00 | 0.00 |
