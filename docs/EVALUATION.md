# Evaluation specification and validity notes

This document describes the implemented four-route **v1** fixture. See [the revised v2 blueprint](BLUEPRINT_V2.md) for the proposed five-route, four-cohort study and the external model-manager boundary. V1 and v2 datasets/results are not interchangeable.

## Purpose

Determine when a local typed decision model is useful for enterprise policy-gating and agent routing, compared with a supervised encoder, lexical retrieval, and a small local generative model. Accuracy, confidence, robustness, operational cost, and abstention behavior matter as much as latency. An agent must never receive authority merely because a classifier predicts a label.

## Design choices

| Original proposal | Implemented interpretation | Reason |
| --- | --- | --- |
| Laya-MLX ModernBERT-large ~421M / 322M | English `aac6fef/laya-mlx` defaults to ModernBERT-large 421M; multilingual `aac6fef/laya-multilingual-mlx` uses mmBERT-base 322M | They are different architectures/checkpoints. Record which one ran. |
| Score 0–100 | Five ordinal Laya levels mapped linearly to 0–100; MPS head predicts continuous 0–100 | Laya score is expected rubric **level**, not natively a 0–100 continuous value. Compare MAE with this qualification. |
| MPS Choice head up to 255 arbitrary options | Initial supervised head has four fixed training labels | A fixed linear head cannot infer unseen arbitrary labels. A separate candidate scoring architecture would be needed for open option sets. |
| Brier loss calibrates probabilities | Brier is a proper scoring loss; evaluate ECE/Brier on held-out data and optionally temperature fit on validation | A loss by itself does not establish calibration. |
| Grammar-constrained `mlx-lm` JSON | Separate prompt-only and finite-candidate logits-mask modes | The latter restricts each output token to a finite set of complete JSON strings. It quantizes score/probability to 101 values and must be tested on a Mac before its schema guarantee is claimed. It is not a general JSON Schema engine. |
| Strictly zero schema failure for typed heads | Typed adapters validate and may fail on version mismatch or exceptions | A claimed zero is a measured result, never an assertion. |
| 1,000 synthetic traces | Seeded templates with grouped negation pairs and split manifest | Prevent pair leakage; synthetic templates are still narrow and must not be presented as external validity. |

## Measurement protocol

1. Generate data with a fixed seed. Keep each inversion pair together in one split. Inspect class distribution, duplicate wording, and label logic before model fitting.
   The runner checks SHA-256 fingerprints of all three generated splits. Test wording families differ from training wording, though this template dataset remains too narrow for deployment claims.
2. Train MPS only on train. Fit temperature on val; never fit on test. Untrained heads have no meaningful accuracy.
3. Run the same test cases for all models. Use a fixed order or record order, and keep the model weights resident. The runner times end-to-end calls using `perf_counter_ns`; adapters synchronize lazy MLX work before returning where supported.
4. Time 500 single-case calls after ten warm-ups for each model. Accuracy runs once over the held-out test set. Report environment and checkpoint identifiers. Tests and metrics are separate from timing so the iterations do not inflate sample support.
5. Report choice accuracy, score MAE, noul accuracy/Brier/ECE, paired inversion accuracy, schema failure rate, exception rate, coverage, and p50/p95. Missing probability fields are `N/A`, never zero.
6. Repeat with real, de-identified operational records and independent human labels before drawing deployment conclusions. Include long-context, ambiguous, out-of-domain, malicious instruction, and policy conflict cases. Measure threshold-dependent false negatives and costs.

## Limitations to investigate

- ModernBERT MPS attention support, memory and latency depend on exact Torch/Transformers releases. A CPU fallback is explicitly forbidden in a Mac GPU benchmark; a failure is reported instead.
- Laya's context includes state, question and criteria. The English checkpoint has a smaller context than the multilingual checkpoint; inspect truncation.
- The lexical baseline retrieves labeled examples. Its probability-like normalized scores are uncalibrated and excluded from Brier/ECE until validation calibration is implemented.
- The generative baseline's JSON answer contains no statistically grounded noul probability. An emitted decimal is treated as a claim, not an intrinsic model probability; its ECE is excluded. Finite output masking can make schema failure rare while distorting the model's choice distribution.
- Benchmark results do not establish determinism, causal understanding, policy compliance, or resistance to prompt injection.

## Verified upstream references (checked 2026-09-30)

- [Laya-MLX Python API and checkpoints](https://github.com/mizorewww/laya-mlx)
- [Multilingual checkpoint model card](https://huggingface.co/aac6fef/laya-multilingual-mlx)
- [ModernBERT Transformers documentation](https://huggingface.co/docs/transformers/en/model_doc/modernbert)
- [MLX-LM project and generation API](https://github.com/ml-explore/mlx-lm)
- [LM Format Enforcer design; potential future grammar integration](https://github.com/noamgat/lm-format-enforcer)

## Checkpoints

**Phase 1:** reproducible data, metric tests, lexical control, error-aware reports. **Phase 2:** Laya and MPS adapter integration on Mac, fixed training and calibration protocol. **Phase 3:** generative baseline, tested grammar mode, real de-identified labels, domain-shift and failure analysis. Each phase produces its own tested results; a missing model is never presented as a win or loss.
