# Revised benchmark blueprint (design review)

Status: **proposed v2 protocol, not implemented or measured**. The existing code and `configs/benchmark_config.yaml` implement the earlier four-route synthetic smoke test. Do not combine v1 and v2 results in one comparison table. Freeze this protocol and the model manifest before collecting v2 test predictions.

## Purpose and ownership

Compare local decision systems on enterprise ingestion and compliance triage: categorical routing, a probability for a precisely stated proposition, and a bounded risk score. The comparison asks about accuracy, calibration, robustness, latency, failures, coverage, and operational fit. A model prediction does not authorize quarantine or any agent action; a separate deterministic policy and audit layer makes that decision.

An **external model manager** installs model software and weights and exposes locally available checkpoints on the target Mac. This repository owns the case contract, adapters, training of experimental heads, validation fits, benchmark execution, and reports. It must accept manager-provided local paths/identifiers and an optional read-only model manifest, preflight their availability, and record their exact revisions and hashes. It must not download, install, update, or select production models as part of a benchmark run. `uv` may install this harness's Python environment; the external manager owns the model lifecycle. Current v1 adapters may resolve upstream IDs on first load, so use offline mode and local checkpoint paths until the preflight boundary is implemented.

## v2 decision contract

> **Update 2026-09-30:** the label definitions below are superseded by rubric `2.1.0-draft` (`docs/RUBRIC_V2.md`). Choice is now the primary event type, Noul is page-now, and Score is priority P1–P4 as an ordinal. Owner, disposition and the reasons are recorded alongside.

| Primitive | Question and target | Output | Important distinction |
| --- | --- | --- | --- |
| Choice | Primary routing category from `routine_audit`, `policy_exception`, `security_escalation`, `data_sovereignty_flag`, `telemetry_heartbeat`, `service_outage` (sixth route added 2026-09-30, see DATASET_PLAN_V2 §2) | Exactly one allowed enum; probabilities if intrinsically available | A fixed six-way trained head cannot handle arbitrary options up to 255 without retraining or candidate scoring. |
| Noul | “Does this payload require immediate human review?” | Probability of `true` in [0, 1] | Quarantine is a separate action/proposition. Do not join “quarantine or manual review” into one ambiguous target. |
| Score | “How urgent is this payload under the versioned risk rubric?” | Number in [0, 100] | An ordinal expected level mapped to 0–100 is identified as such; compare both MAE and ordinal agreement. |

Version the route definitions, precedence when multiple flags apply, Noul review threshold, score anchors, and the exact state/question/criteria text. Keep secondary tags (for example, sovereignty plus security) separate from the primary Choice target. Capture an `uncertain`/`needs_adjudication` annotation for conflicting policies. In a shared-task evaluation, every candidate sees the same evidence and semantic criteria; prompt syntax may differ by API and must be recorded. Unsupported primitives are `N/A` with coverage, never silently approximated as native output.

## Data and labels

Use the proposed **500-case pilot** as a versioned *synthetic fixture*: direct 40% (200), negation/inversion 25% (125), jargon 20% (100), boundary 15% (75). Aim for 70/15/15 train/validation/test. Group inversion pairs and wording families before splitting, so exact 350/75/75 counts and exact per-cohort percentages may need adjustment; write actual counts and group IDs to the manifest. Hold out distinct templates, not just newly generated identifiers. Include all five routes and all three primitives in each split, publish a label audit, and ensure a test case is never used to choose prompts, thresholds, model settings, or calibration.

Boundary examples should have a **documented adjudication process**. A target probability of 0.45–0.60 cannot be inferred from a single deterministic synthetic label. Record independent reviewer votes or repeated outcome frequencies where available; otherwise report boundary accuracy, disagreement, and abstention/coverage separately and avoid claiming probabilistic truth. The 75-case pilot test would contain only about 30/19/15/11 cases across the four cohorts before splitting by primitive and route, so ECE and close model rankings will be unstable. Report denominators and paired confidence intervals, and add a larger sealed, independently labeled set before claiming comparative superiority or deployment readiness. Include out-of-domain, long-context, conflicting-instruction, and policy-conflict sets.

## Candidate matrix

| Candidate | Primary comparison | Native task coverage / qualification | Status in repository |
| --- | --- | --- | --- |
| BM25 | Lexical nearest labeled example | Choice, hard Noul, heuristic Score; no calibrated probability | v1 adapter exists; retarget v2 labels |
| Laya-MLX | Off-the-shelf typed encoder | Choice/Noul/ordinal Score; identify English 421M versus multilingual 322M checkpoint | v1 adapter exists; Mac integration pending |
| Von | Off-the-shelf typed encoder | Choice/Noul/ordinal Score; pin version and raw Noul posterior; disable optional chains for single-pass arm, measure chains separately | adapter planned |
| GLiClass | Zero-shot classification | Choice directly; binary Noul only with explicit label mapping and validation; continuous Score unsupported | adapter planned; pin uni- or bi-encoder checkpoint |
| SemIf | First-token/option-logit decision | Exact task-specific verbalizers and probability extraction need validation; same base checkpoint as generative arm where supported | adapter planned |
| Generative MLX | Full local JSON generation | Typed parse for all tasks; generated decimal is not intrinsically calibrated | v1 prompt and finite-candidate modes exist; Mac integration pending |
| ModernBERT MPS | Domain-tuned encoder | Fixed routes, bounded Score, Noul; fit calibration on validation only | v1 four-route adapter/training exists; retarget v2 |
| Small generative (Gemma family) | Smallest viable local LLM: can a sub-1B to ~2B decoder do the triage at all, and at what latency and memory? | Same served path as the other generative arms (llamaCPPManager, GGUF and/or MLX); prompt-JSON and grammar-constrained modes; typed parse for all tasks. Size points: ~270M, ~1B, and the existing Gemma 4 E2B entry. Exact checkpoints, quantization and revisions are pinned from the Mac inventory (Q1). The manager's KNOWN-ISSUES records `gemma-3-270m` (GGUF) already run on the M4. **Excluded:** `gemma-270m-compliance-mlx` was fine-tuned for compliance questions, a different domain, so it is not a candidate for the alert-triage use case. It may be used only in a future compliance-domain use case, as a separate arm with its training data disclosed | added 2026-10-01 (D20); no adapter code beyond the shared served-generative adapter (WS8) |
| Gemma + LoRA heads | Domain-tuned decoder | Experimental; verify hidden-state access, MPS/MLX training feasibility, memory, and exact base model | feasibility gate, then adapter/training |

Use a **native capability table** as well as the harmonized table. Do not rank a candidate on a metric it cannot supply. GLiClass is not generically a bi-encoder: its default pipeline is a uni-encoder, and a distinct bi-encoder checkpoint exists. Current Von documents version 1.3, Apple MPS, a default Noul probability band, and optional multi-pass chains; a “Von-1.0 single-pass” row would mix checkpoint and execution modes. SemIf now documents an MLX backend. “Gemma E2B” refers to Gemma 4 E2B; “Gemma 4B” needs an exact generation, size, checkpoint, and license/access resolution. Avoid calling any forward pass `O(1)` without specifying input length, options, and prefill cost.

## Training and calibration

Fit Choice with cross-entropy, Score with Huber on a normalized target (and return 0–100), and Noul with Brier. Store loss weights, label counts, seeds, training code revision, and checkpoint hash. A 350-case synthetic training set is a functional exercise, not evidence that a 2B–4B decoder was successfully domain-adapted. Run a small feasibility trial on the actual device before committing the Gemma arm.

Fit binary logit temperature or Platt scaling on **validation** using a proper scoring objective such as Brier or NLL; choose the method and hyperparameters without seeing test. Report validation and test Brier/ECE with bin counts, reliability diagram, and uncertainty intervals. ECE is a diagnostic rather than a stable objective on a small validation split. Keep shipped raw and validation-calibrated probabilities as separate arms, especially for Von's `raw` mode. Check threshold-dependent false negatives, false positives, and abstention under explicit costs; do not equate a low ECE with safe policy action.

## Timing and reporting

- Batch size 1, identical held-out cases, loaded weights resident, 20 untimed calls on the exact path, then **100 timed calls for a pilot**. Use a longer run (for example, 500 timed calls and repeated sessions) for stable p95 and thermal sensitivity. Accuracy is computed once per held-out case; timing repeats do not increase the sample size for accuracy.
- Time full synchronous request handling including formatting, tokenization, inference, decoding, parsing, and device synchronization. Record input/output tokens, prompt length and truncation, precision/quantization, warm-up count, timing sample count, run order, chip/memory, OS, package versions, checkpoint revision/hash, power mode, and model-manager manifest identity. Exclude model load and training; report them separately if relevant.
- Distinguish prompt-only JSON, finite-token JSON, and any genuine grammar integration. Finite candidate masking quantizes Score/Noul and may distort distributions. Record schema parse/type/range failures, backend exceptions, unsupported cases, and OOM separately. A typed adapter's schema failure is measured, not assumed zero.
- The summary includes per-model/purpose coverage, p50/p95, Choice accuracy, paired inversion accuracy, cohort accuracy, Score MAE, Noul accuracy/Brier/ECE, schema failure and exception rates, with numerator/denominator and confidence intervals. Mark unavailable and unsupported as `N/A`; never invent Mac results on a Linux host.

## Implementation sequence and acceptance gates

1. **Freeze v2 domain and dataset:** versioned rubric/precedence, cohort generator, grouped splits, manifest and independent label audit. Add contract and leakage tests. Preserve v1 as a separate dataset/config.
2. **Preflight model boundary:** local manifest/path resolution, no download during benchmark, exact revision recording, per-candidate capability declarations, and clear unavailable status. The manager itself stays outside this repo.
3. **Off-the-shelf comparison:** retarget BM25/Laya/generative, then integrate and Mac-test Von, GLiClass, SemIf one at a time. Pin exact model/runtime versions and align the direct-logit/generative base model when feasible.
4. **Domain adaptation:** retarget ModernBERT and validation calibration; gate Gemma LoRA/head work on an actual M4 feasibility trial. Report trained and untrained states distinctly.
5. **Pilot and sealed evaluation:** run tests, all supported Mac adapters and timing protocol, produce raw provenance plus a Markdown report; follow with independent real labels and confidence intervals. A missing candidate is explicitly unavailable and does not block a transparent partial report.

## Primary upstream references (checked 2026-09-30)

- [Laya-MLX](https://github.com/mizorewww/laya-mlx)
- [Von SDK and runtime](https://github.com/wfzyx/von)
- [GLiClass](https://github.com/Knowledgator/GLiClass)
- [SemIf-OpenJev](https://github.com/TheoLeeCJ/SemIf-OpenJev)
- [MLX-LM](https://github.com/ml-explore/mlx-lm)
- [Gemma 4 E2B model card](https://huggingface.co/google/gemma-4-E2B)
