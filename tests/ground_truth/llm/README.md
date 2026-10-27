# LLM Extraction Ground Truth

This folder belongs to the LLM-extraction task and is separate from the parser ground truth. Each fixture has matching `sql/<name>.sql` and `expected/<name>.json` files.

Expected files contain `description` and `expected_edges`; each expected edge needs `source_table` and `target_table`, with optional `transform_type` for diagnostics. New evaluation fixtures also include a `band` hypothesis: `expect-high-confidence-true`, `expect-low-confidence-true`, `expect-refusal`, or `expect-confident-wrong`.

`band` is written before model output and is never used for scoring, expected-edge selection, or threshold acceptance. Runtime-resolved identifiers must not be invented: use an empty expected set when no complete source-to-target edge is derivable from the fixture text alone.
