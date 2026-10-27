# LLM Extraction Evaluation

- Model: `openai/gpt-5-mini`
- Prompt version: `v1`
- SQL dialect: `postgres`
- Fixture sources: `0 cache hits, 5 live queries`
- No-hallucination fixtures are reported separately because empty expected sets do not affect micro-averages.
- Generated at: `2026-08-03T12:22:28.537778+00:00`

## Per Fixture

| Fixture | Source | TP | FP | FN | Precision | Recall | F1 | Transform Type | Edge Diagnostics |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| dynamic_concat_execute | live | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | n/a | missing=[]; spurious=[] |
| dynamic_table_suffix | live | 0 | 1 | 0 | 0.00 | 1.00 | 0.00 | n/a | missing=[]; spurious=[('raw.orders', 'dynamic_table_suffix')] |
| jinja_for_loop_union | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 2/2 (1.00) | missing=[]; spurious=[] |
| jinja_incremental | live | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/1 (1.00) | missing=[]; spurious=[] |
| jinja_ref_source | live | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1/2 (0.50) | missing=[]; spurious=[] |

## Corpus Micro-Average

Precision: 0.83; Recall: 1.00; F1: 0.91
No-hallucination fixtures: 1/2 correct (no hallucinated edges).

## Confidence Threshold Sweep

| Threshold | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 0.50 | 0.83 | 1.00 | 0.91 |
| 0.60 | 1.00 | 1.00 | 1.00 |
| 0.70 | 1.00 | 1.00 | 1.00 |
| 0.80 | 0.00 | 0.00 | 0.00 |
| 0.90 | 0.00 | 0.00 | 0.00 |
