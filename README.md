# Alt-JEV-LABs

Local-first experiments for typed decision models on Apple Silicon. The first experiment compares Laya-MLX, a supervised ModernBERT multi-head model, a BM25 nearest-example baseline, and a local generative MLX model on the same `choice`, `score`, and `noul` tasks.

This is a **measurement harness**, not a claim that any model is deterministic, calibrated, or safe for policy enforcement. A valid JSON response can still be wrong; a probability is only useful after calibration on representative data. The synthetic dataset is a plumbing and failure-mode probe, not evidence of production accuracy.

## Quick start

Use Python 3.12 on an Apple Silicon Mac. Model weights download only on explicit setup or first model load. Record the checkpoint revision before publishing results.

```bash
uv sync --extra apple --extra test
uv run python -m data.synthetic_generator --output data/splits --count 1000 --seed 42
uv run pytest -q
uv run python -m evaluation.benchmark_runner --models lexical,laya,mps,generative --iterations 500 --warmup 10
```

`mps` requires a trained checkpoint. Train on the generated train split first:

```bash
uv run python -m training.train_heads --epochs 3 --output artifacts/mps-heads.pt
```

The runner writes `benchmark_results.md` and `artifacts/benchmark_results.json`. It records failures and unavailable models rather than inventing measurements. To run only the lexical baseline while preparing weights, use `--models lexical`. The report contains `N/A` for unsupported metrics (for example, a generative model does not expose calibrated probabilities from a JSON answer).

## Evaluation contract

- **Choice:** exactly one label from the options supplied by the case. The initial MPS head supports the four fixed routing labels; other option sets must be trained separately.
- **Score:** a 0–100 severity target. Laya uses an ordinal five-level rubric; its expected level is multiplied by 25. This conversion is recorded because it is not the same as continuous regression.
- **Noul:** probability of a true proposition. Threshold 0.5 measures classification; Brier and ECE assess probabilities separately.
- **Timing:** one complete API call per sample, including tokenization, formatting, and synchronized inference. Loading, download, training, and warm-up are excluded. P50/P95 are over 500 calls after 10 untimed calls by default; hardware, software, model revision, prompt length, power mode, and precision must accompany a report.
- **Invalid output:** parse/type/range failure is counted as schema failure. Backend exceptions are counted separately. Do not silently coerce them into success.

The generative adapter currently uses `mlx-lm` with a strict JSON parser after generation and a JSON-only prompt. This is **prompt-constrained, not grammar-constrained decoding**. Its schema failure rate therefore measures the mode actually run. A grammar-backed mode must be separately implemented and labeled before claiming schema enforcement. See [design and validity notes](docs/EVALUATION.md).

## Repository guidance

- Keep data, labels, configuration, calibration fits, and provenance versioned or hashed. Keep downloaded weights, personal traces, and generated artifacts out of Git.
- Split by `pair_id` to prevent a negation pair crossing train/validation/test. Train and calibrate only with the train/validation splits, then freeze choices before measuring test.
- Compare the same cases and state/question text. Report coverage and failures alongside accuracy. Do not turn synthetic labels into security policy.
- Prefer explicit adapters and typed results. Fail loudly on unsupported option sets, missing checkpoints, and incompatible library APIs.
- Preserve local-first operation. Network access is limited to deliberate dependency and checkpoint downloads; inference requires no cloud service.
- Work in a branch for changes after this initial scaffold; review before merging into `main`. Explain changes, run the relevant tests, and record what could not be exercised on Apple Silicon.

## Layout

`configs/` defines model IDs and benchmark settings; `data/` generates and stores examples; `models/` holds adapters; `training/` fits the MPS head and calibration; `evaluation/` computes metrics and reports; `tests/` checks contracts and benchmark logic. The full execution specification and departures from it are in [docs/EVALUATION.md](docs/EVALUATION.md).

## Status

The code can be checked on a non-Mac host for syntax and contract behavior. Full MLX and MPS integration, lockfile resolution, model downloads, and benchmark results require an Apple Silicon run. No measured results are included in this scaffold.
