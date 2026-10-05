# Handoff: continue on the M4 Mac

Written 2026-10-04 by `claude-cloud-ws1-01` (Linux cloud session). Read this, then `AGENTS.md`, `docs/OWNERSHIP.md` and `docs/TRACKER.md`. If this file and the tracker disagree, the tracker wins; fix this file in the same PR.

**Everything below was verified on Linux only. No model has ever been run. No Apple Silicon step has ever been run.** Do not describe any earlier result as measured.

## What exists on `main`

| Area | State |
| --- | --- |
| Rubric 2.4.0 (`docs/RUBRIC_V2.md`, `data/rubric.py`, `configs/domains/v2_rubric.json`) | Frozen. Do not edit without a recorded decision. |
| Seeds (`data/seeds/registry.jsonl`, 330 records) + synthetic filler | Merged. Loghub templates and Atomic Red Team only. |
| Cohort generator (`data/generator_v2.py`, `docs/GENERATOR_V2.md`) | Merged. 560 cases: A 200, B 125, B' 60, C 100, D 75; splits 394/83/83. Missing: leave-one-source-out, stream replay (S6), label-budget subsets (S7). |
| Chat module (`ingest/`, `docs/CHAT_MODULE.md`) | Merged, off by default. |
| Real-data guidance (`docs/REAL_DATA_GUIDE.md`) | Guidance only (D26). No real data in the project. |
| Seed licenses (`docs/SEED_SOURCE_LICENSES.md`) | Logstash Apache-2.0, Vector MPL-2.0, Wazuh GPLv2 verified; others unverified. |
| Test suite | 151 passed on Linux at the time of writing (more after in-flight PRs). |

## In flight when this was written (check before starting)

Two PRs from `claude-cloud-ws1-01` subagents may have merged since. Look at `docs/TRACKER.md` (WS4 row, decision D27) and `git log origin/main` first.

- **WS4**: v2 runner, cohort results table, scorecard and report (`evaluation/*`, `docs/EVALUATION_V2.md`).
- **Reference-only seed sources**: `data/seed_references.py`, `data/seeds/references.json`, `docs/SEED_REFERENCES.md`. Vendor-licensed seeds are fetched locally and never committed or published.

Do not redo either. If a PR is still open, do not edit the same files.

## Release of ownership

`claude-cloud-ws1-01` releases **WS8** (manager preflight, `generative_managed` adapter, encoder manifest) and the **retarget of `models/*` and `training/*` to the six routes and the P1-P4 task** to the Mac agent, because both need the hardware. `claude-cloud-ws1-01` will not edit `models/*` or `training/*` until the Mac agent hands them back. Claim them by writing your agent ID in the tracker's WS8 Owner cell in the PR that starts the work, and add your row to the Agent IDs table in `docs/OWNERSHIP.md`. Pick an ID that does not collide with `claude-cloud-ws1-01` or `codex-ebook-companion-01` (suggested: `codex-mac-01`).

## Steps on the Mac

1. `git clone https://github.com/lballaty/Alt-JEV-LABs && cd Alt-JEV-LABs && git checkout main`.
2. `uv sync --extra apple --extra test && uv run pytest -q`. Expect at least 151 passed. The Apple extras have never been installed on any host; record every failure verbatim. Report which tests skip or fail only because of hardware.
3. `llamacpp-manager status --json > artifacts/manager_status.json`. Keep it out of Git (local paths). It is the input for the WS8 preflight.
4. `llama-server --version`. The manager policy requires build >= b10154.
5. Regenerate the dataset locally to confirm it is deterministic on this host: see `docs/GENERATOR_V2.md`. Output goes to the git-ignored `artifacts/cohort_v2`. Do not commit it.
6. Ask the owner the questions below, then start WS8.

## Questions only the owner (Libor) can answer

| # | Question |
| --- | --- |
| Q1 | Which llamaCPPManager model names and ports are the generative candidates? Which base (not fine-tuned) Gemma sizes and quantizations are installed (D20)? |
| Q2 | `HF_HUB_OFFLINE=1` permanently on the MLX entries, or a benchmark-only profile? |
| Q3 | Which encoder/classifier candidates (Laya English 421M vs multilingual 322M, Von, GLiClass, SemIf, ModernBERT heads, Gemma LoRA)? Where are they stored? |
| Q4 | p95 latency budget; confirm the memory cap 96 GB with a 16 GB reserve (D12). An unset latency budget must show "not evaluated", never pass. |
| Q8 | Non-served checkpoints: inventory in the manager (M2) or in this repo? |
| — | `AGENTS.md` rule 6 still says "seek review before merging to main". Owner instruction D21 overrides it, but the file was not edited (an automated block prevented it). Owner to edit. |

Q7 (real data) is decided optional (D26); do not ask for it.

## Work order

1. **WS8 preflight and adapters.** Preflight from `manager_status.json` with exact revisions and hashes recorded. A `generative_managed` adapter against the served endpoint with explicit temperature and seed (the manager defaults to 0.7). Verify grammar, JSON-schema and logprob request fields against the real `llama-server` build, not from memory (`AGENTS.md` rule 8). The benchmark consumes already provisioned checkpoints and must not download or manage them.
2. **Retarget** the adapters and the MPS heads from five/four routes to the six v2 routes and the three outputs (event type, page-now, priority P1-P4). Unsupported primitives are `N/A` with coverage, never approximated.
3. **Run the v2 test split** through the WS4 runner for each available candidate. Seed fixed, batch size 1, 20 untimed calls then 100 timed calls (BLUEPRINT_V2 timing protocol). Record peak unified memory including the model and harness; the gate is min(cap, 128 GB - measured baseline - reserve); mark a run invalid if memory pressure leaves normal or swap grows.
4. **Report** with full provenance and the synthetic-data banner (WS4 output). Update the tracker with measured results, clearly separated from anything unmeasured.

## Test scenarios (D36) — read before WS8

`docs/TEST_SCENARIOS.md` defines S0 (alternatives on public datasets with the 37-dataset paper's templates, compared with its published Jev results), S1 (the primary result: our alert-triage cases asked through one canonical Jev-shaped request) and variations. For WS8 this means: adapters should accept the canonical S1 request (state plus typed questions with described criteria; a 4-level priority Score), and generative candidates should use the option-probability readout (one forward pass, no text generation) as the baseline, with JSON generation kept only as a variation. `claude-cloud-ws1-01` builds the S1 request builder and metrics; coordinate through the tracker (WS12) before changing shared interfaces. S0 needs a one-time dataset download on the Mac as a preparation step (never during a timed run, never committed).

## Findings for WS8 (2026-10-05, see `docs/STATUS_REVIEW.md` 5b)

- Pin the Laya revision: `configs/benchmark_config.yaml` and `models/laya_runner.py` load `aac6fef/laya-mlx` with no revision.
- If Von is used: set `--noul-decision raw` and record whether chains are on; its default Noul is not a probability.
- If GLiClass is used: pass a `torch.device("mps")`, not a string, or it runs on CPU.
- Jev-compatible local servers exist (upstream Laya, Von, Decider); they may simplify adapters. Provision weights through the model manager; never download during a run.

## Rules that apply

- **D35:** this repository is public. Never put private repository names, URLs, paths, commits or content in files, commit messages or PR text; say "the ebook workspace" or "the example repository".

- **D32:** label every latency with its network path (on-device, local loopback, or remote) and, where a network is involved, measure the network delay separately when possible and report it next to the end-to-end time.

- **D21:** merge to `main` yourself once tests pass, and update `docs/TRACKER.md` in the same PR. Owner can revoke.
- Never commit weights, secrets, local-path manifests, vendor-licensed seed text, or generated datasets built from local-only seeds.
- Never edit the frozen rubric. Never claim a result that was not run. No model output may authorize an action (`AGENTS.md` rule 5).
- Results on this dataset are synthetic-only and support model comparison, not a deployment decision (D26).
- Start every session from a fresh `git fetch origin main`.
