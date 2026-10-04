# v2 cohort runner, report and selection scorecard (WS4)

Status: **implemented and tested on Linux with stub candidates. No model result exists.** Everything in this note concerns the evaluation layer for the v2 *synthetic, generated* dataset from `data/generator_v2.py` (rubric 2.4.0). Nothing here was run on Apple Silicon. The v1 path (`evaluation/benchmark_runner.py`, `metrics.py`, `reporter.py`) is unchanged and its tests pass unchanged.

Owner: `claude-cloud-ws1-01`. Design sources: `docs/PRACTICAL_EVAL_V2.md` section 5 and 4a, `docs/DATASET_PLAN_V2.md` section 4, `docs/GENERATOR_V2.md`, tracker decisions D8, D11-D13.

## Files

| File | Purpose |
| --- | --- |
| `evaluation/v2_data.py` | Loader (manifest verified, fail loudly), question-to-task mapping, model-input rendering |
| `evaluation/v2_metrics.py` | Pure metrics: Wilson, seeded cluster bootstrap, cohort cells, consequential errors, cost, calibration, latency |
| `evaluation/v2_runner.py` | Runs a candidate list through the unchanged `BaseDecisionModel` interface; timing; validation-fitted calibrated arm |
| `evaluation/scorecard.py` | Hard gates, cost-weighted components, verdict |
| `evaluation/v2_report.py` | Markdown and JSON report with full provenance |
| `evaluation/v2_cli.py` | `python -m evaluation.v2_cli` |
| `configs/selection_scorecard.yaml` | Placeholder thresholds, weights and cost matrix (D13); `p95_ms_max: null` |
| `tests/test_v2_*.py`, `tests/conftest.py`, `tests/v2_fixtures.py` | 114 new tests; stubs live in `tests/v2_fixtures.py` |

```bash
uv run python -m data.generator_v2 --output artifacts/cohort_v2 --seed 42
uv run python -m evaluation.v2_cli --data-dir artifacts/cohort_v2 --models lexical      # plumbing check by default
uv run --extra test pytest -q
```

`--purpose` defaults to `plumbing_check`. A plumbing report carries a banner saying the numbers prove the harness runs and are not evidence, and its scorecard can only say `insufficient evidence`. Use `--purpose measurement` deliberately, on the target Mac, with candidate provenance filled in. Outputs go under `artifacts/` (git-ignored).

## Loading and split discipline

`load_v2_dataset(dir)` calls the generator's own `verify_manifest` (hashes, sizes, case counts, full re-lint), then re-hashes the exact bytes it parses, then checks: dataset kind is `synthetic_generated` and `real_data` is false; each row sits in its split file; `questions` equals `["event_type","page_now","priority"]`; cohorts are known; case ids are unique; cohort D is ungraded; `expected` equals the stored `label` (the generator's lint re-derives `label` but does not compare `expected`, which scoring reads); the rubric file hash equals the manifest's. Any failure raises `DatasetIntegrityError`; nothing is repaired or skipped. The CLI exits 2 without writing a report.

The headline uses **test only**. Validation is loaded only to fit calibration (and later thresholds). Train is loaded only when a candidate must index or fit on it (the lexical control) and is never scored. Targets are `None` in every DecisionCase handed to an adapter for val/test, so an adapter cannot read the answer.

## Question to task mapping (explicit)

| v2 question | Adapter primitive | Candidate output | Harness scoring |
| --- | --- | --- | --- |
| `event_type` | `choice`, options = the six rubric event types | one option | exact match with `expected.choice` |
| `page_now` | `noul` | P(page now) | `p >= 0.5` is a page; compared with `expected.noul` |
| `priority` | `score` 0-100, higher is more urgent | a number | binned P1 >= 75, P2 >= 50, P3 >= 25, else P4; ordinal scoring |

The priority bins are a measurement convention (PRACTICAL_EVAL_V2 section 1), not an answer key. The question text given to the adapter states the bins. One v2 case therefore makes three adapter calls. Model input is `render_state`, an allow-list of `event` and `context` (version `v2-state-render-1`); labels, evidence, archetype, spoof and pair metadata never reach the model. `event.signal` is shown by default (see review flags).

## Outcomes and denominators

Every (case, task) call ends as `ok`, `schema_failure` (`SchemaFailure`), `unsupported` (`ModelUnavailable`, or a task outside the adapter's optional `v2_supported_tasks`, which is then not called) or `exception` (anything else). Statuses are never mixed and a backend error is never scored as a wrong answer (AGENTS.md rule 8).

* Accuracy-type cells use **answered** calls as the denominator.
* Safety figures also have a **strict** form where a non-answer counts as a miss: must-page recall and B' escalation kept. The scorecard gates use the strict form.
* Schema-failure and exception rates are over *attempted* calls; unsupported rate and coverage are over all calls.
* Every cell is numerator, denominator and a Wilson 95% interval. A zero denominator is `N/A` with a reason in the JSON, never 0. Unsupported tasks are `N/A`, never approximated; the cost total is `N/A` if any task is wholly unsupported.

## Cohort matrix

Rows are candidate x arm; column groups are A, B, B', C, D and pooled (A+B+B'+C, graded cases only). Metrics: event-type accuracy, page-now accuracy, must-page recall (answered and strict), false-page rate, priority exact, within-one and ordinal MAE (in P levels), paired-inversion accuracy (B only; a pair is right when page-now is right on **both** the A parent and the B child, plus a label-flip-only subset; pairs with a non-answered member are excluded and counted as incomplete), B' escalation kept (B' only), schema-failure rate, exception rate, unsupported rate, coverage. Cells not defined for a cohort are `N/A (not defined for this cohort)`.

Consequential errors are listed first with case ids: a missed page in B or B' is an *improper suppression* (a change window or a payload claim kept an event that should have escalated); a missed page elsewhere is a *missed must-page*; non-answers on must-page cases are listed separately.

**Cohort D** has no gold. No accuracy, no must-page recall, no ECE. Reported: coverage, failure rates, agreement with provisional labels **only if a case carries them** (the generator ships none, so it is `N/A`, and it is named agreement, not accuracy), and abstention, which is `N/A` because the adapter interface has no abstain output (it is not inferred from a probability near 0.5).

**Paired differences** between candidates are computed on identical cases (answered by both) for five per-case metrics, with a seeded percentile bootstrap that resamples whole **template/pair groups** (`manifest.groups`), not single cases, because cases within a group are not independent. Raw and calibrated arms of one candidate are not compared with each other (identical decisions).

## Calibration

Pooled only (A+B+B'+C), with Brier, ECE (the existing `evaluation.metrics.ece`) and per-bin counts; no cohort-level ECE; cohort D excluded. Only probabilities whose source is `model` count; BM25 hard labels and generated LLM claims make the arm `N/A`. The calibrated arm is derived from the raw arm's outputs (the model is not run again): logit temperature scaling, fitted with `training.calibrate.fit_temperature` on **validation** page-now probabilities and applied unchanged to test. Temperature scaling fixes 0.5, so decisions equal the raw arm's and only probabilities change. Validation rows are shown for transparency and are in-sample for the calibrated arm; the test row is the out-of-sample figure. No threshold selection is implemented yet (threshold is fixed at 0.5).

## Latency

A separate table. Method (`TIMING_METHOD`, recorded in every report): `perf_counter_ns` around one complete synchronous `evaluate(case).validate(case)` call, batch size 1, per (case, task) call on the test split, cycling through answered calls; load, training and untimed warm-up excluded; accuracy is scored once and timing repeats add no accuracy samples. `--iterations 0` (default) skips timing and the table says `not measured`.

## Scorecard

Config: `configs/selection_scorecard.yaml`, strictly validated (unknown keys, weights not summing to 1.0, bad thresholds raise). Everything in it is a **placeholder** (D13); the report prints "PLACEHOLDER" next to the cost matrix and weights.

Gate states: `pass`, `fail`, `inconclusive` (the interval straddles the threshold), `not_evaluated` (input missing, unset, wrong hardware, or the suite is not built). `not_evaluated` is never a pass.

| Gate | How it is evaluated here |
| --- | --- |
| runs offline on target | attested input `operational.offline_verified`; absent is `not_evaluated` |
| licence OK | attested input `operational.license_ok`; absent is `not_evaluated` |
| supports all three tasks | added by WS4 (not in section 5): the decision needs all three outputs; any unsupported call fails it |
| schema-valid rate >= 0.995 | valid / attempted over all test calls (exceptions count against it) |
| must-page recall >= 0.95 | strict, cohorts A and B' (S1+S3 as written), Wilson bound rule |
| B' escalation kept >= 0.95 | strict; hard gate for spoof resistance |
| false pages per 1k <= 20 | needs the S6 stream, not built: `not_evaluated` unless a value is supplied |
| p95 latency | `p95_ms_max` is **null (Q4 open): "not evaluated"**; even when set it needs >= 100 timing samples and a hardware string containing `M4` |
| peak memory | D12: effective gate = `min(cap 96, host 128 - baseline_other - reserve 16)` GB; needs measured peak and preflight baseline; run is `not_evaluated` (invalid, not failed) if memory pressure left normal or swap grew or either was not recorded; cap and reserve are configurable placeholders |
| chat module (off by default) | S9 gates when enabled; `not_evaluated` without S9 results; weights rescale (core x 0.85) |

`gate_rule: wilson_bound` (default) passes only if the Wilson lower bound clears the threshold and fails only if the upper bound is below it; `point` compares the estimate. Weighted components computable today: cost-weighted error (S1+S2, `1 - cost / worst possible cost`, placeholder matrix) and spoof robustness (S3); S4, S5, S6, S7, explainability and ops fit are `not_evaluated` with the reason. No silent renormalization: the row shows weight coverage and a partial score labelled not comparable to a full score.

Selection output per candidate arm: `not recommended` (an evaluated gate failed), `recommended` (every gate passed **and** `selection.min_weight_coverage` of the weight was evaluated **and** the run is a `measurement`), otherwise `insufficient evidence`, each with reasons and the three costliest failures. `min_weight_coverage` defaults to 1.0, so `recommended` is not reachable until S4-S7 and the other components exist. A plumbing check never yields a verdict either way. Every scorecard prints that **a pass is not deployment approval**, that synthetic results cannot support a deployment decision (only S8 can), and that a deterministic authorization and audit layer is still required (AGENTS.md rule 5).

## Report contents

Markdown and JSON, both from one dict. Top: `dataset: SYNTHETIC (generated), not real data`, the plumbing/measurement banner, the not-approval notice. If the manifest lists Loghub seeds the Loghub block is added automatically (URL, ISSRE 2023 and ISSTA 2024 citations as in README, licence file, D8 note); a test keeps the citation strings equal to README's. Provenance: dataset kind, generator and version, dataset seed, rubric version and file hash (manifest and current), manifest sha256, split file hashes, seed sources, validity limits; harness seed, bootstrap size, render version, event-signal flag, page threshold, timing method; hardware, platform, Python and package versions, power mode and memory sampling (both "not recorded"/"not run"); per candidate model id, revision, precision, prompt/template, seed, and any extra keys (each "not recorded" if the caller gave none, never invented), calibration fit, timing status, first errors. The JSON also keeps raw per-call outcomes for test and val. S9/chat results are accepted as an optional input and rendered in their own section, never pooled; no S9 runner exists.

## Adapter retargeting needed (documented, not done; WS8)

The runner drives the unchanged adapters. `--models laya,mps,generative,generative_finite` loads them via `benchmark_runner.load_model` from `--v1-config` after forcing `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; a load failure is an `unavailable` row with the reason. On this Linux host all four report unavailable (Apple extras absent): that is the only path of these four that was exercised.

* **BM25 (`lexical`):** works as is on the mapping; hard labels, no calibration (N/A).
* **ModernBERT MPS:** fixed four labels (`security_alert`, `schema_mismatch`, `telemetry_heartbeat`, `audit_log`); it raises `ModelUnavailable` for the six-type option set, which surfaces as unsupported (N/A, coverage) as intended. Needs retraining on the six event types and a P1-P4 ordinal head, a v2 training/calibration entry point (`training/*` reads v1 splits), and a `v2_supported_tasks` declaration.
* **Laya:** `choice` takes the options as criteria, so the six types may work unchanged; the `score` path uses five configured levels times 25 and is not validated against P1-P4. Needs a Mac check and an explicit level-to-P mapping.
* **Generative (prompt and finite):** options and question are in the prompt, so six types work in principle; the page-now number is a `generated_claim` (calibration N/A); finite mode quantizes to 101 values. WS8's served-endpoint adapter (D10) replaces local `mlx_lm` loading; pin temperature and seed.
* **Contract additions to consider (edit `models/base.py`, WS8):** an optional abstain output (needed for cohort D and S5), an optional `provenance()` returning model id, revision and precision, and `v2_supported_tasks` on each adapter.

## Running it on the Mac (not done yet)

Per `docs/HANDOFF_MAC.md` (20 untimed calls, 100 timed calls, batch size 1). Real revisions, precision and the measured gate inputs come from the Mac session through `--candidate-info`; anything omitted stays "not recorded" or "not evaluated".

```bash
uv run python -m data.generator_v2 --output artifacts/cohort_v2 --seed 42
uv run python -m evaluation.v2_cli --data-dir artifacts/cohort_v2 --models lexical,laya \
  --v1-config <local config naming local checkpoints> --warmup 20 --iterations 100 --seed 42 \
  --purpose measurement --candidate-info artifacts/candidate_info.json
```

`candidate_info.json` holds `{"laya": {"provenance": {"model_id": ..., "revision": ..., "precision": ..., "prompt_template": ..., "seed": ...}, "operational": {"offline_verified": true, "license_ok": true, "peak_memory_gb": ..., "baseline_other_gb": ..., "memory_pressure_normal": true, "swap_grew": false}}}`. The memory numbers must be sampled by the Mac session (method open, D11/D12). Set `hard_gates.p95_ms_max` in a copy of the scorecard config once the owner answers Q4; until then the p95 gate stays "not evaluated". `evaluation/v2_runner.py` imports `training.calibrate.fit_temperature` (read-only); if the Mac agent moves it while retargeting `training/*`, update that one import.

## Verified on this Linux host / not verified

| Item | Status |
| --- | --- |
| 114 new tests pass; full suite 265 passed (151 existing + 114 new), v1 tests unchanged | Verified |
| Statement coverage of new modules (`--cov-branch`): `v2_data` 100%, `v2_report` 100%, `v2_runner` 100%, `scorecard` 99%, `v2_metrics` 99%, `v2_cli` 98% (the miss is the `__main__` guard) | Verified |
| Metric, CI, N/A, unset-gate, memory-formula, tamper, provenance and citation behaviour, against hand-computed values and stubs | Verified |
| Plumbing run of the lexical BM25 control on the generated cases (CLI, `--iterations` small) | Run only to prove the pipeline; its numbers are not recorded anywhere and are not evidence |
| Any MLX, MPS, Laya or generative run; offline-mode behaviour of real adapters | **Not run** (needs the Mac) |
| Memory sampling (peak, baseline, pressure, swap), latency on the M4 Max, power mode | **Not run** |
| Any v2 measurement of a real candidate | **None exists** |

## Assumptions (conservative choices where the docs were ambiguous)

1. Accuracy denominators are answered calls; strict forms exist for safety figures and gates use them.
2. Gates use the Wilson bound rule, so small samples are `inconclusive`, not pass.
3. Improper suppression = missed page in B or B'; missed must-page elsewhere.
4. `wrong_queue` cost uses an event-type mismatch as a proxy for a wrong owner queue.
5. A non-answer is charged the worst wrong answer for its case and task in the cost metric.
6. Must-page gate cohorts are A and B' as section 5 says (S1+S3); B and C must-page recall are reported, not gated.
7. `spoof_escalation_kept_min` is 0.95, borrowed from the chat module's `spoof_recall_min` because section 5 names B' a hard gate without a core number. Owner to confirm.
8. Paired-inversion needs the page-now answer right on both members.
9. Page threshold 0.5; priority bins as above; both are conventions.
10. Rubric file hash mismatch raises (`allow_rubric_drift` exists in Python, not in the CLI).

## Review flags

1. **Sample size.** The test split is 83 cases (30 A, 18 B, 9 B', 15 C, 11 D); 72 are graded. With the Wilson rule the schema gate (0.995) needs roughly 765 attempted calls to pass, the test split gives 249. At pilot size most gates will be `inconclusive` and `recommended` is out of reach by construction. If the owner wants a different rule, set `gate_rule: point`, knowing that is weaker evidence.
2. **Wilson intervals assume independent cases**; pair and template groups violate that, so the cell intervals are optimistic. Only the paired bootstrap clusters by group (31 test groups, so those intervals are also rough).
3. **Signal shortcut.** `event.signal` is a detector name that nearly spells the event type, and the change block's `expected_signals` repeats signal names even with `--hide-event-signal`. The rubric's expected-activity rule needs the signal, so it is shown, but a lexical model can exploit it. A held-out-signal ablation is not built.
4. **Cohort D** cannot yield defer quality until two-reviewer adjudication (WS6) and an abstain output exist.
5. **`min_weight_coverage` 1.0** means no recommendation until S4-S7, explainability and ops fit exist; lower it only by an owner decision.
6. Attested gates (offline, licence) are caller-supplied, not verified by this code.
7. Placeholders needing owner values: p95 budget (Q4), memory cap and reserve (D12), cost matrix and weights (D13), spoof threshold (flag 7 above).
8. `pytest-cov` is not a project dependency; coverage was measured with `uv run --with pytest-cov`.
