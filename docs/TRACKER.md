# v2 evaluation tracker

Last updated: 2026-09-30 (end of cloud session; next session continues on the M4 Mac). **Update this file in every PR that changes plan, intent or status.** Nothing in the v2 plan has been measured yet. Status values: `Not started` · `Planned` · `In progress` · `Blocked` · `Ready for review` · `Merged`.

## Intent

Build a practical, reproducible evaluation for choosing a local decision model to put in front of SOC/SRE queues. It must rank candidates on offline operation, correct routing, must-page recall, resistance to spoofed authorization, labeling cost, latency and throughput on the target Mac. The output is a selection scorecard, not a showcase for one model. Classifier output never authorizes an action (AGENTS.md rule 5).

Plan documents:

| Doc | Branch | Purpose |
| --- | --- | --- |
| `docs/BLUEPRINT_V2.md` | `main` (PR #1) | v2 protocol, candidate matrix, training/calibration, timing |
| `docs/DATASET_PLAN_V2.md` | `main` | Seed sources, license review, cohorts, split and leakage rules, workstreams |
| `docs/PRACTICAL_EVAL_V2.md` | `main` | Selection-oriented suites S1–S9, event+context format, chat module, scorecard |
| `docs/MODEL_MANAGER_INTEGRATION.md` | `main` | Boundary with llamaCPPManager (arionrepo/llamacppmanager @ b7d27f9): preflight, served generative adapter, encoder manifest |
| `docs/MANAGER_IMPROVEMENTS.md` | `main` | Proposed llamaCPPManager API/CLI (M1–M10) and UI (U1–U5) changes to support testing |

## Decisions log

| # | Date | Decision | Where recorded |
| --- | --- | --- | --- |
| D1 | 2026-09-30 | 500-case pilot, four cohorts (A 40 / B 25 / C 20 / D 15), grouped 70/15/15 split | BLUEPRINT_V2 |
| D2 | 2026-09-30 | Add `service_outage` as sixth route | DATASET_PLAN_V2 §2 |
| D3 | 2026-09-30 | Loghub: use templates only with synthetic entities; never vendor raw log lines | DATASET_PLAN_V2 §1 |
| D4 | 2026-09-30 | Authorization/negation comes from a structured `context` block; payload-text authorization is tested as spoof (B′) | PRACTICAL_EVAL_V2 §2–3 |
| D5 | 2026-09-30 | Chat ingestion in scope as an optional module (S9), scored and reported separately | PRACTICAL_EVAL_V2 §3a |
| D6 | 2026-09-30 | OpenEnv SRE triage source excluded until verified | DATASET_PLAN_V2 §1 |
| D7 | 2026-09-30 | Grow pilot to 560: add 60 B′ spoofed-authorization cases on top of the 500 | DATASET_PLAN_V2 §3 |
| D8 | 2026-09-30 | Loghub used non-commercially (research); preliminary results published publicly in this repo. Obligations: ship Loghub license notice with derived templates, reference repo URL, cite ISSRE 2023 + ISSTA 2024 in README and every report using Loghub-derived data. Revisit before any commercial use | DATASET_PLAN_V2 §1a |
| D9 | 2026-09-30 | Repo licensing: code Apache-2.0, docs/results CC BY 4.0; NOTICE names Libor Ballaty as original author and requires the original repo URL in redistributions; third-party data keeps its own terms | `LICENSE`, `LICENSE-DOCS`, `NOTICE` |
| D10 | 2026-09-30 | Models on the M4 are managed by llamaCPPManager; the benchmark consumes served endpoints and never loads/downloads generative weights itself | MODEL_MANAGER_INTEGRATION |
| D11 | 2026-09-30 | M4 memory budget for testing ≈ 80 GB including the model: peak unified-memory footprint of the model server/process plus harness during the timed run. A candidate above it fails the hard gate. The measurement method is to be fixed in WS8/WS4 on the Mac | PRACTICAL_EVAL_V2 §5 |
| D12 | 2026-09-30 | Host is an M4 Max with 128 GB unified memory. Memory cap raised to a proposed 96 GB (from 80), with a 16 GB reserve. The effective gate per run = min(cap, 128 − measured baseline of other processes − reserve). A run is marked invalid if memory pressure leaves normal or swap grows. Supersedes D11's number; cap/reserve are placeholders to confirm | PRACTICAL_EVAL_V2 §5 |

## Open decisions

All open owner decisions are consolidated under **Open questions** at the end of this file (Q1–Q7). The former O3 is now Q7 and O4 is now Q4/Q5.

## Workstreams

| WS | Scope | Owner | Branch | Status | Blocked by | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| — | Finite JSON decoding, validation calibration, v2 blueprint | Other agent | `feat/finite-json-calibration` | Merged (PR #1) | — | Six routes applied to BLUEPRINT_V2 on the plan branch |
| — | Dataset + practical eval plan, this tracker | This session | `plan/v2-datasets-test-structure` | Merged (PR #2) | — | main merged in; README license + Loghub credits added |
| WS1 | Seed registry: Loghub templates, ART seeds, synthetic entity filler, tests | Cloud session `session_016suEmxQMsUKD66MEcF2kow` | `feat/v2-seed-registry` (via PR #3) | Merged (PR #3) | — | 330 seeds (Loghub 322: BGL 120, Linux 118, OpenStack 43, OpenSSH 27, HDFS 14; ART 8), pinned commits + sha256; no IPs in templates (checked). 8 tests collected (session summary said 13). |
| WS2 | v2 rubric: 6 routes, precedence, page policy, P1–P4 anchors, `needs_human`, context schema | This session | `feat/v2-rubric` | Merged (PR #3) | — | `configs/domains/v2_rubric.json` (2.0.0-draft), `data/rubric.py`, 16 tests; needs independent SOC/SRE review before freeze |
| WS3 | Cohort generator (A/B/B′/C/D), leak lint, leave-one-source-out, stream replay, label-budget subsets | Unassigned | — | Planned | WS1 (WS2 draft available) | New files only; target 560 cases (D7) |
| WS4 | Runner/reporter: cohort matrix, CIs, scorecard output | Unassigned | — | Planned | O4 (thresholds); other branch merged | Touches the same files as the other agent. Reporter must auto-add the Loghub citation when the dataset manifest lists Loghub seeds (D8) |
| WS5 | Verify OpenEnv, ATT&CK terms, Zenodo license, alternative telemetry sources | Unassigned | — | Blocked | Hugging Face/Zenodo egress blocked here | Run on Mac or allowlist hosts |
| WS6 | S8 own-data protocol: de-identification, labeling guide, two-labeler agreement | Unassigned | — | Planned | O3 | |
| WS7 | Chat module: `ingest/chat.py`, thread schema, chat de-identification, synthetic threads, S9 | Unassigned | — | Planned | — (WS2 draft available) | Modular, toggled in config |
| WS8 | Manager boundary: `status --json` preflight + provenance, `generative_managed` adapter (prompt-JSON / grammar / logprob modes), encoder local-path manifest | Unassigned | — | Planned | Mac for final verification | Encoders are not served by the manager |
| WS9 | llamaCPPManager improvements for testing: must-haves M1 manifest/provenance, M3 readiness, M4 physical-footprint memory, M5 offline, M6 test lock; UI U1–U5 | Unassigned (manager repo) | — | Planned | Mac inventory (Q1–Q3); push access to `arionrepo/llamacppmanager` | Harness fallbacks listed per item |

## Verified vs not verified

| Item | Status |
| --- | --- |
| v1 harness tests (5/5) and lexical-only smoke run on Linux | ✅ Verified 2026-09-30 |
| v2 rubric contract tests (16) + full suite 23/23 on Linux | ✅ Verified 2026-09-30 |
| WS1 seed registry merged with rubric branch: full suite 31/31 on Linux | ✅ Verified 2026-09-30 |
| llamaCPPManager interface (read from source @ b7d27f9) | ⚠️ Read only; not run against the M4 |
| Loghub in-repo license, template counts | ✅ Verified 2026-09-30 |
| Zenodo license, OpenEnv dataset, ATT&CK terms | ❌ Not verified (egress blocked / not fetched) |
| Any Apple Silicon run (MLX, MPS, Laya, generative) | ❌ Not run |
| Any v2 measurement | ❌ None exists |

## Risks

| Risk | Mitigation |
| --- | --- |
| Synthetic content leaks the answer (v1 BM25 = 1.000) | Leak lint in WS3; held-out wrapper/template families |
| Payload-text authorization teaches a prompt-injection bypass | B′ suite as hard gate; authorization only via context |
| Pilot test split too small for stable rankings | Report n and CIs; S8 real data before any deployment claim |
| MLX servers can download on HF cache miss; manager query defaults to temperature 0.7 | `HF_HUB_OFFLINE=1` on benchmark models; benchmark sets temperature/seed explicitly (WS8) |
| Parallel agents editing the same files | WS1–WS3, WS7 add new files only; WS4 waits for the other branch to merge |

## Handoff: continue on the M4 Mac

Branch state at handoff: PR #2 (plan, licensing) and PR #3 (WS1 seed registry + WS2 rubric) are **merged into `main`**. Everything is Linux-tested only.

Steps on the Mac:

1. `git clone https://github.com/lballaty/Alt-JEV-LABs && cd Alt-JEV-LABs && git checkout main`.
2. `uv sync --extra apple --extra test && uv run pytest -q`: expect 31 passed. The Apple extras have never been installed; record any failure verbatim.
3. `llamacpp-manager status --json > artifacts/manager_status.json`: keep it out of Git (it contains local paths). It is the input for the WS8 preflight.
4. `llama-server --version`: confirm the build is ≥ b10154, per the manager policy.
5. Answer the questions below, then continue: WS8 (preflight + `generative_managed` adapter, verifying grammar/JSON-schema/logprob request fields on the real build) → WS3 generator → WS7 chat → WS4 scorecard.

## Open questions (owner: Libor)

| # | Question | Why it matters | Blocks |
| --- | --- | --- | --- |
| Q1 | Which llamaCPPManager model names/ports are the generative candidates? | Defines the served generative arms | WS8 |
| Q2 | `HF_HUB_OFFLINE=1` permanently on the MLX entries, or a benchmark-only group/profile? | Prevents downloads during runs | WS8 |
| Q3 | Which encoder/classifier candidates to include (Laya English 421M vs multilingual 322M, Von, GLiClass, SemIf, ModernBERT heads, Gemma LoRA)? Where are they stored locally? | The manager does not serve these; they need a local-path manifest | WS8, candidate matrix |
| Q4 | p95 latency budget; confirm memory cap 96 GB / reserve 16 GB (D12) | Sets the remaining scorecard hard gate | WS4 |
| Q5 | Scorecard cost matrix and thresholds (placeholders in PRACTICAL_EVAL_V2 §5) | Ranking among candidates that pass the gates | WS4 |
| Q6 | Who reviews the rubric (routes, precedence: sovereignty above outage?) before freeze? | The rubric must be frozen before the sealed test split | WS3 freeze |
| Q7 | Real data: 200–300 de-identified events (S8) and chat threads (S9). Source, and who de-identifies? | Only real data supports a deployment conclusion | WS6, S8/S9 |
| Q8 | Non-served checkpoints (Laya, ModernBERT heads, GLiClass, Von, SemIf): inventory in the manager (M2) or in this repo? | Single source of model provenance | WS8, WS9 |
