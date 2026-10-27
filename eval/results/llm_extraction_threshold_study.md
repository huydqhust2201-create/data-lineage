# LLM Extraction — Confidence Threshold Study

> Corpus: 21 fixtures / 29 expected edges (`tests/ground_truth/llm/`)
> Model: `openai/gpt-4.1-mini` · Prompt version: `v1` · Dialect: `postgres` · Temperature: `0.0`
> Run 1 cache: `eval/.cache-exp1` · Run 2 cache: `eval/.cache-exp1-run2` (21 entries each)
> Sources: `llm_extraction_eval_expanded_run1.md`, `llm_extraction_eval_expanded_run2.md`, and a
> direct re-derivation from both caches. No production code or shared configuration was changed.

---

## 1. Verdict

**Recommend `confidence_threshold = 0.5`.** Both runs support it, and the support is stronger than an
F1 comparison: **0.5 strictly dominates 0.7 on precision *and* recall in both runs.**

| Cut | Run 1 P / R / F1 | Run 2 P / R / F1 |
| --- | --- | --- |
| **0.5** | **0.967 / 1.000 / 0.983** | **0.935 / 1.000 / 0.967** |
| 0.7 | 0.963 / 0.897 / 0.929 | 0.929 / 0.897 / 0.912 |

Moving 0.5 → 0.7 costs 3 of 29 true edges (−10.3% recall) and **gains no precision** — it loses a
little (−0.004, −0.006), because the false positives it leaves behind sit *above* both cuts. There is
no axis on which 0.7 is better.

**Thresholds 0.6 and 0.7 remain indistinguishable**, now confirmed on 21 fixtures across two runs:
zero edges fall in `[0.6, 0.7)` in either run. The original "both score 1.0" was one measurement
reported twice, and expanding the corpus 4× did not change that — as predicted, because the prompt's
rubric only ever emits `{0.3, 0.5, 0.7, 0.9}`.

**Thresholding cannot fix hallucination.** It raises no-hallucination performance from 4/7 to 6/7 and
then stops permanently. See §6.

---

## 2. Raw precision, recall, and F1 (no filtering)

| | Run 1 | Run 2 | Δ |
| --- | ---: | ---: | ---: |
| Predicted edges | 33 | 34 | +1 |
| True positives | 29 | 29 | 0 |
| False positives | 4 | 5 | +1 |
| False negatives | 0 | 0 | 0 |
| **Precision** | 0.879 | 0.853 | −0.026 |
| **Recall** | 1.000 | 1.000 | 0.000 |
| **F1** | 0.935 | 0.921 | −0.014 |

Recall is **1.000 in both runs** — the model found every one of the 29 hand-authored edges, twice.
All observed error is false-positive error, and the entire run-to-run difference is one extra
hallucinated edge in run 2.

Against the 5-fixture baseline (P 0.833 / R 1.000 / F1 0.909), the expanded corpus reports slightly
*higher* precision. That is not an improvement in the model — it is 24 additional true edges diluting
a roughly constant number of hallucinations. Precision here is largely a function of how many
easy-to-resolve fixtures the corpus contains, which is exactly why the raw number is a weak signal.

## 3. Threshold 0.5 versus 0.7

Full sweep, re-derived from both caches (identical to the published reports):

| Cut | Run 1 TP/FP/FN | Run 1 P / R / F1 | Run 2 TP/FP/FN | Run 2 P / R / F1 |
| ---: | --- | --- | --- | --- |
| 0.0 | 29 / 4 / 0 | 0.879 / 1.000 / 0.935 | 29 / 5 / 0 | 0.853 / 1.000 / 0.921 |
| 0.3 | 29 / 4 / 0 | 0.879 / 1.000 / 0.935 | 29 / 5 / 0 | 0.853 / 1.000 / 0.921 |
| **0.5** | **29 / 1 / 0** | **0.967 / 1.000 / 0.983** | **29 / 2 / 0** | **0.935 / 1.000 / 0.967** |
| 0.6 | 26 / 1 / 3 | 0.963 / 0.897 / 0.929 | 26 / 2 / 3 | 0.929 / 0.897 / 0.912 |
| 0.7 | 26 / 1 / 3 | 0.963 / 0.897 / 0.929 | 26 / 2 / 3 | 0.929 / 0.897 / 0.912 |
| 0.8 | 6 / 1 / 23 | 0.857 / 0.207 / 0.333 | 6 / 2 / 23 | 0.750 / 0.207 / 0.324 |
| 0.9 | 6 / 1 / 23 | 0.857 / 0.207 / 0.333 | 6 / 2 / 23 | 0.750 / 0.207 / 0.324 |

**Applying the pre-registered decision rule** (plan §6 Step 5). Let *L* = correctly-predicted edges
with confidence in `[0.5, 0.7)`.

- **|L| = 3 in both runs** — all three from `jinja_ref_in_loop_literal_list`, the Group B for-loop
  fixture. The `|L| ≥ 1` branch applies, so a recommendation is permitted.
- **Recall cost of 0.5 → 0.7:** 3/29 = **10.3%**, identical in both runs.
- **Precision gain of 0.5 → 0.7:** **none.** Run 1 −0.004, run 2 −0.006. Removing three true edges
  from a set whose remaining false positives sit at 0.90 makes the ratio slightly worse.
- **F1 gap (0.5 over 0.7):** +0.054 run 1, +0.055 run 2. Run-to-run variance at a fixed cut is 0.014
  (at 0.5) and 0.017 (at 0.7), so the gap is roughly 3× the noise and has the same sign in both runs.
  The condition "recommend only if the F1 difference exceeds run-to-run variance" is met.

**Threshold 0.8 — the current config default — is disastrous.** It discards 23 of 29 true edges
(recall 0.207) while *lowering* precision to 0.857/0.750, because the confident hallucinations survive
it. Every true edge the model is sure about sits at 0.7, so a 0.8 gate is above almost the entire
true-edge population. This is not a tuning subtlety; 0.8 is on the wrong side of the model's modal
confidence.

**0.6 vs 0.7 is unanswerable and always will be.** Both runs report `edges in [0.6, 0.7): 0`. The
rubric in `_SYSTEM_PROMPT` enumerates four anchor values and the model complies literally, so the
band between them is empty by construction, not by sampling accident. Observed distribution:

| Confidence | Run 1 | Run 2 |
| ---: | ---: | ---: |
| 0.30 | 3 (all FP) | 3 (all FP) |
| 0.50 | 3 (all TP) | 3 (all TP) |
| 0.70 | 20 (all TP) | 20 (all TP) |
| 0.90 | 7 (6 TP, 1 FP) | 8 (6 TP, 2 FP) |

Three usable cut points exist — below 0.5, between 0.5 and 0.7, and between 0.7 and 0.9. Any
"threshold tuning" finer than that is measuring nothing.

## 4. Repeatability across the two runs

`temperature=0.0` did **not** produce identical output. The two runs are genuinely independent
samplings (their cached responses differ), so the comparison is valid.

**Stable across runs:**
- The true-positive set: the same 29 edges, edge for edge, both times.
- Recall: 1.000 / 1.000.
- The confidence assigned to every true edge — all 26 non-0.9 TPs sat at the same value in both runs.
- The `[0.6, 0.7)` emptiness, and the identity of 0.6 and 0.7.
- Which no-hallucination fixtures failed: the same three, both times.
- `|L| = 3`, from the same fixture.

**Unstable across runs:**
- False positives: 4 → 5. `dynamic_from_column_value` produced 2 spurious edges in run 1 and 3 in run
  2, and the spurious target for the variable `t` changed (`t -> fct_registry` vs
  `t -> dynamic_from_column_value`).
- Corpus F1: 0.935 → 0.921 (Δ 0.014, within the plan's ≤0.05 acceptance bound).
- `transform_type` labels flipped substantially: `jinja_nested_macro_ref` scored 0/2 then 2/2;
  `jinja_alias_shadows_model` scored 1/1 then 0/1.

**Reading:** the model's *extraction* is highly repeatable; its *hallucination* and its
*transform-type labelling* are not. Every point of run-to-run variance came from one fixture's
spurious edges. Two runs is a very weak variance estimate (n=2), so treat 0.014 as an existence proof
that variance is non-zero, not as a calibrated error bar.

## 5. No-hallucination performance

Seven fixtures declare `expected_edges: []`. Raw score: **4/7 in both runs.**

| Refusal fixture | Run 1 | Run 2 | Confidence of spurious edges |
| --- | --- | --- | --- |
| `dynamic_table_suffix` | clean | clean | — |
| `jinja_undefined_var` | clean | clean | — |
| `jinja_var_no_default` | clean | clean | — |
| `macro_definition_only` | clean | clean | — |
| `dynamic_concat_execute` | 1 FP | 1 FP | 0.30 |
| `dynamic_opaque_function` | 1 FP | 1 FP | 0.30 |
| `dynamic_from_column_value` | 2 FP | 3 FP | **0.90** (×1 / ×2) plus 0.30 |

The model reliably refuses when the unknown is *syntactically* obvious — an undefined Jinja variable,
a `var()` with no default, a macro with no query, a target name glued from a runtime value. It fails
when the unknown requires *semantic* judgement:

- `source_table` and `t` are PL/pgSQL variables holding a table name; the model emits them as if they
  were tables (confidence 0.30 — it is appropriately unsure).
- `get_source_table(run_id)` is a function call; emitted as a table name (0.30).
- **`meta.registry` is a real table, but it is read only to *look up a name*, not as a data source.**
  The model emits `meta.registry -> dynamic_from_column_value` at **0.90** in both runs, and run 2 adds
  `fct_registry -> dynamic_from_column_value` at 0.90 as well.

That last row is the important one, and it is the reason for §6.

## 6. Threshold filtering is not a hallucination fix

These are two different problems, and the data separates them cleanly.

**What a threshold at 0.5 does fix.** It removes every 0.30-confidence false positive — 3 of 4 in run
1, 3 of 5 in run 2 — at zero cost to recall. No-hallucination goes **4/7 → 6/7** in both runs. This is
real, free, and reproducible: the model's low-confidence output is genuinely low-quality, so its
self-reported confidence carries usable signal at the bottom of the scale.

**What no threshold can fix.** `dynamic_from_column_value` stays contaminated at **every** cut from
0.0 to 0.9, in both runs, because its false edges carry the model's *highest* confidence value. The
score never reaches 7/7:

| Cut | 0.0 | 0.3 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| No-hallucination (both runs) | 4/7 | 4/7 | **6/7** | 6/7 | 6/7 | 6/7 | 6/7 |

A confident hallucination is a **reasoning error, not a calibration error**. The model understood the
SQL and drew the wrong lineage conclusion: it saw `select table_name into t from meta.registry` and
recorded the metadata table as an upstream dependency of `fct_registry`. Nothing in a confidence
distribution distinguishes that from a correct high-confidence edge, so no cut point can separate
them. Raising the gate only destroys recall — at 0.8 the corpus loses 23 true edges and still ships
the same bad ones.

**The two fixes that would work, neither of which is a threshold:**

1. **Prompt-level.** Teach the extractor that a table read solely to *obtain an identifier* — a
   registry, config, or metadata lookup feeding dynamic SQL — is not a lineage source of the target.
   This is the only lever for the `meta.registry` class, since both endpoints are syntactically valid
   table names and only intent distinguishes them.
2. **Validation-level**, in `to_lineage_edges`, cheap and deterministic. Two of the four observed
   false-positive shapes are mechanically detectable without any model change:
   - a source containing `(` or `)` is a function call, not a table (`get_source_table(run_id)`);
   - a bare single-token source that matches a name `declare`d or `select … into` in the same file is
     a variable, not a table (`t`, `source_table`).

   These are the same class of guard the service already applies for unresolved Jinja markers and
   self-loops, and they would eliminate the 0.30-confidence false positives outright — making the
   threshold's main benefit redundant and leaving the gate free to serve its actual HITL purpose.

**A note on what `confidence_threshold` means.** PRD FR-4 defines it as a *human-review gate* — edges
below it are queued for confirmation, not discarded — whereas this sweep measures *discarding* below
the cut. The recommendation of 0.5 holds under both readings, but for different reasons. As a review
gate, 0.5 queues exactly the 3 junk edges and auto-accepts 30–31 good ones, which is an excellent
triage ratio. What it cannot do under either reading is catch the 0.90 hallucinations: no gate value
below 0.9 reviews them, and a gate above 0.9 reviews the entire corpus. The confident-hallucination
class is structurally outside what this control can reach.

## 7. Limitations of the 21-fixture corpus

Read the numbers above with these in mind.

1. **One edge is worth 3.4 points of recall.** With 29 expected edges, differences under ~0.03 are one
   edge. The entire precision gap between the two runs (0.026) is a single hallucinated edge.
2. **The recall-cost measurement rests on one fixture.** All three `[0.5, 0.7)` true edges come from
   `jinja_ref_in_loop_literal_list`. Delete that one file and thresholding looks free again — which
   was precisely the artifact this expansion was built to eliminate. The 0.5-over-0.7 result is
   directionally solid (it reproduced exactly, and 0.5 also wins on precision) but it rests on a
   narrow base.
3. **Recall is at ceiling.** 1.000 in both runs, zero false negatives ever observed. The corpus cannot
   discriminate anything on recall below a 0.6 cut, and cannot detect a model that is merely *good*
   from one that is *perfect* at finding edges.
4. **Confidence has four levels, so only three cut points exist.** No corpus of any size can answer
   0.6-vs-0.7 under prompt `v1`. Answering it requires changing the rubric — which bumps
   `PROMPT_VERSION` and invalidates every cached response here.
5. **Our ability to predict model confidence from fixture design is poor.** Only 1 of 5 Group B
   fixtures (`expect-low-confidence-true`) actually produced low confidence; two produced the *highest*
   (0.90). Both Group D "confident-wrong" baits were answered correctly. Fixture design steers what is
   *asked*, not what the model *feels*.
6. **n = 2 runs.** Enough to prove `temperature=0.0` is not deterministic here, not enough to
   characterise the distribution.
7. **Single annotator, single model, single dialect, single prompt version.** Ground truth was authored
   by the extractor's own owner (carried-over caveat), so these figures measure agreement with our
   labels. Everything is `openai/gpt-4.1-mini` on `postgres` under prompt `v1`.
8. **Fixtures are short and synthetic.** Real dbt projects have long files, cross-file macro imports,
   and package dependencies. Nothing here tests multi-file resolution, and `transform_type` proved too
   unstable across runs (0/3 → 2/2 swings) to be trusted at all — it is not part of precision/recall,
   and on this evidence it should not be relied on downstream.

## 8. Recommendations

1. **Set `confidence_threshold = 0.5`** (currently 0.8). Supported by both runs, on both axes, with
   the F1 gap ~3× run-to-run variance. Requires a change to `src/config.py` — shared configuration, so
   it is a team decision, not part of this study.
2. **Do not tune between 0.6 and 0.7.** They are the same cut under prompt `v1`. Any future report
   presenting them as two agreeing results is reporting one number twice.
3. **Treat the confident-hallucination class as a separate work item.** It caps no-hallucination at
   6/7 regardless of threshold. Add the deterministic validation guards from §6 first — they are cheap
   and cover two of the four observed false-positive shapes — then consider the prompt change for the
   `meta.registry` class.
4. **If continuous confidence is wanted, change the rubric deliberately**, bump `PROMPT_VERSION`, and
   re-baseline. Expect every cached response in `eval/.cache*` to be invalidated.
5. **Before trusting any of this operationally**, add fixtures that produce false negatives — the
   corpus has never seen one — and get a second annotator onto Groups B and D.
