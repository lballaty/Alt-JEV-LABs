# Alt-JEV-LABs

Local-first experiments for typed decision models on Apple Silicon. The first experiment compares Laya-MLX, a supervised ModernBERT multi-head model, a BM25 nearest-example baseline, and a local generative MLX model on the same `choice`, `score`, and `noul` tasks.

This is a **measurement harness**, not a claim that any model is deterministic, calibrated, or safe for policy enforcement. A valid JSON response can still be wrong; a probability is only useful after calibration on representative data. The synthetic dataset is a plumbing and failure-mode probe, not evidence of production accuracy.

## Quick start

Use Python 3.12 on an Apple Silicon Mac. An external model manager provisions the model software and checkpoints. Point the benchmark configuration and training `--backbone` argument at its local paths (or already cached, pinned identifiers); record their exact revisions. Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` for a benchmark run so an unresolved identifier fails locally instead of fetching weights. The checked-in v1 configuration contains illustrative upstream identifiers and needs local resolution on the Mac.

```bash
uv sync --extra apple --extra test
uv run python -m data.synthetic_generator --output data/splits --count 1000 --seed 42
uv run pytest -q
uv run python -m training.train_heads --backbone /path/from/model-manager/ModernBERT-base --epochs 3 --output artifacts/mps-heads.pt
uv run python -m training.calibrate --backbone /path/from/model-manager/ModernBERT-base --validation data/splits/val.jsonl --checkpoint artifacts/mps-heads.pt
uv run python -m evaluation.benchmark_runner --models lexical,laya,mps,generative,generative_finite --iterations 500 --warmup 10
```

`mps` requires both a trained checkpoint and a validation-only calibration file.

The runner writes `benchmark_results.md` and `artifacts/benchmark_results.json`. It records failures and unavailable models rather than inventing measurements. To run only the lexical baseline while preparing weights, use `--models lexical`. The report contains `N/A` for unsupported metrics (for example, a generative model does not expose calibrated probabilities from a JSON answer).

The [revised v2 blueprint](docs/BLUEPRINT_V2.md) reviews the proposed five-route, four-cohort, eight-candidate study and the external model-manager boundary. It is a design review; the commands above still run the earlier four-route v1 fixture. Do not interpret v1 output as results for the v2 protocol.

## Evaluation contract

- **Choice:** exactly one label from the options supplied by the case. The initial MPS head supports the four fixed routing labels; other option sets must be trained separately.
- **Score:** a 0–100 severity target. Laya uses an ordinal five-level rubric; its expected level is multiplied by 25. This conversion is recorded because it is not the same as continuous regression.
- **Noul:** probability of a true proposition. Threshold 0.5 measures classification; Brier and ECE assess probabilities separately.
- **Timing:** one complete API call per sample, including tokenization, formatting, and synchronized inference. Loading, download, training, and warm-up are excluded. P50/P95 are over 500 calls after 10 untimed calls by default; hardware, software, model revision, prompt length, power mode, and precision must accompany a report.
- **Invalid output:** parse/type/range failure is counted as schema failure. Backend exceptions are counted separately. Do not silently coerce them into success.

The generative adapter has two separate modes. `generative` uses a JSON-only prompt and strict parser, with no token restriction. `generative_finite` masks logits to tokenizations of complete JSON candidates (up to 255 choice labels, 101 integer scores, or 101 probability increments). This enforces a finite output set, **not a general JSON Schema grammar**, and quantizes numeric answers. Both modes require Apple Silicon integration tests. See [design and validity notes](docs/EVALUATION.md).

## Repository guidance

- Keep data, labels, configuration, calibration fits, and provenance versioned or hashed. Keep downloaded weights, personal traces, and generated artifacts out of Git.
- Split by `pair_id` to prevent a negation pair crossing train/validation/test. Train and calibrate only with the train/validation splits, then freeze choices before measuring test.
- Compare the same cases and state/question text. Report coverage and failures alongside accuracy. Do not turn synthetic labels into security policy.
- Prefer explicit adapters and typed results. Fail loudly on unsupported option sets, missing checkpoints, and incompatible library APIs.
- Preserve local-first operation. The external model manager provisions weights; benchmark execution uses locally available models and must not download them. Harness dependency installation is separate from model provisioning.
- Work in a branch for changes after this initial scaffold; review before merging into `main`. Explain changes, run the relevant tests, and record what could not be exercised on Apple Silicon.

## Layout

`configs/` defines model IDs and benchmark settings; `data/` generates and stores examples; `models/` holds adapters; `training/` fits the MPS head and calibration; `evaluation/` computes metrics and reports; `tests/` checks contracts and benchmark logic. The full execution specification and departures from it are in [docs/EVALUATION.md](docs/EVALUATION.md).

## Status

The code and lockfile were checked on a Linux host for syntax and contract behavior. MLX/MPS installation and integration, model downloads, and Apple Silicon benchmark results require a run on the target Mac. No Apple Silicon measurements are included in this scaffold.
