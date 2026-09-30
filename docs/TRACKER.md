# v2 evaluation tracker

Last updated: 2026-09-30 (end of cloud session; next session continues on the M4 Mac). **Update this file in every PR that changes plan, intent or status.** Nothing in the v2 plan has been measured yet. Status values: `Not started` · `Planned` · `In progress` · `Blocked` · `Ready for review` · `Merged`.

## Intent

Build a reusable, local-first way to compare viable solutions for a concrete decision use case and choose the best fit under stated requirements. Each use case supplies a decision contract and rubric, representative and adversarial cases, candidate approaches and simple baselines, failure costs, operational constraints and acceptance criteria. The result is a comparative scorecard: screen hard requirements first, show consequential errors and operational trade-offs for feasible candidates, and explain the recommendation or why evidence is insufficient. Performance estimates apply only under the tested conditions. The scorecard supports a named human decision owner, who records whether the combined evidence and residual risk justify a specified pilot or deployment; a test pass is not an automatic certification or release decision.

The first reference use case is an operational triage gateway in front of SOC/SRE and privacy workflows. Its v2 evaluation ranks candidates on offline operation, correct event classification and priority, must-page recall, resistance to spoofed authorization, labeling cost, latency and throughput on the target Mac. A separate proposed gateway would handle live ingress, policy enforcement and dispatch; this repository is the evaluation harness. Classifier output never authorizes an action (AGENTS.md rule 5). See [project intent and adaptation](PROJECT_INTENT.md).

Plan documents:

| Doc | Branch | Purpose |
| --- | --- | --- |
| `docs/BLUEPRINT_V2.md` | `main` (PR #1) | v2 protocol, candidate matrix, training/calibration, timing |
| `docs/DATASET_PLAN_V2.md` | `main` | Seed sources, license review, cohorts, split and leakage rules, workstreams |
| `docs/PRACTICAL_EVAL_V2.md` | `main` | Selection-oriented suites S1–S9, event+context format, chat module, scorecard |
| `docs/MODEL_MANAGER_INTEGRATION.md` | `main` | Boundary with llamaCPPManager (arionrepo/llamacppmanager @ b7d27f9): preflight, served generative adapter, encoder manifest |
| `docs/MANAGER_IMPROVEMENTS.md` | `main` | Proposed llamaCPPManager API/CLI (M1–M10) and UI (U1–U5) changes to support testing |
| `docs/MANAGER_HANDOFF.md` | `main` | How the llamaCPPManager work (delivered as a bundle) gets into that repo: commit hashes, checksum, remaining items H1–H9, prompt for the next agent |

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
| D13 | 2026-09-30 | Scorecard starts with the placeholder cost matrix and thresholds (PRACTICAL_EVAL_V2 §5); revisit after the pilot | PRACTICAL_EVAL_V2 §5 |
| D14 | 2026-09-30 | Rubric review 1 received: do not freeze 2.0. Rubric restructured as 2.1.0-draft: event type, owner, impact, urgency, disposition and priority are separate; no precedence ranking, score bands or criticality bonus; the expected-activity match requires the signal; correlation requires the same type and failure mode; human-review reasons; worked examples W1–W9. Scored outputs: event type, page-now, priority P1–P4 | RUBRIC_V2.md, reviews/RUBRIC_REVIEW_1.md |
| D15 | 2026-09-30 | Rubric review 2: do not freeze 2.1. 2.2.0-draft keeps notification separate from priority (explained or attached events keep their priority; an attached repeat takes the incident's), defines response classes P1–P4 first, replaces 'human review, no target' with provisional labels that have a triage owner and deadline, and treats log claims as untrusted but observations as evidence. Worked examples W1–W9 plus W4b, W4c, W6b | RUBRIC_V2.md, reviews/RUBRIC_REVIEW_2.md |
| D16 | 2026-09-30 | Rubric review 3 (two reviewers; SOC, SRE and DPO roles all approve with changes) → 2.3.0-draft: acknowledgement and fact-finding clocks separated; every page states its immediate action and containment decision; fact-finding expiry escalates to the owner's lead; pages go to 24x7 teams (DPO → SOC verifier, platform/compliance → SRE); P4 split into scheduled and retained; 'set once' reworded to 'from current evidence'; W4c/W4d trend cases, W6b clarified, W9 pages SOC, W9b approved transfer | RUBRIC_V2.md, reviews/RUBRIC_REVIEW_3.md |
| D17 | 2026-09-30 | Rubric review 4: B approves (SOC/SRE/DPO roles, all signed by one person); A approves with changes → 2.4.0-draft: containment is a recorded decision with options, not automatic; W4d justifies same-day review (alternate replica, short projection); DPO review within 4 business hours, SOC owns out-of-hours fact-finding; approval record must include revision, test command, result and a named approver per role | RUBRIC_V2.md, reviews/RUBRIC_REVIEW_4.md |
| D18 | 2026-09-30 | Rubric **frozen as 2.4.0** by the project owner after reviewer A's corrections were applied and rubric code coverage reached 100% (lines and branches; 60 rubric tests, 75 total). Validity limits recorded: roles signed by one person; reviewer A did not re-confirm 2.4; tests prove the code matches the chosen answers, not operational practice | RUBRIC_V2.md freeze record |
| D19 | 2026-09-30 | Reviewer A confirmed rubric 2.4 with no comments; both reviewers approve. The 'not re-confirmed' validity limit is removed (record-only) | RUBRIC_V2.md freeze record |

## Open decisions

All open owner decisions are consolidated under **Open questions** at the end of this file (Q1–Q7). The former O3 is now Q7 and O4 is now Q4/Q5.

## Workstreams

| WS | Scope | Owner | Branch | Status | Blocked by | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| — | Finite JSON decoding, validation calibration, v2 blueprint | Other agent | `feat/finite-json-calibration` | Merged (PR #1) | — | Six routes applied to BLUEPRINT_V2 on the plan branch |
| — | Dataset + practical eval plan, this tracker | This session | `plan/v2-datasets-test-structure` | Merged (PR #2) | — | main merged in; README license + Loghub credits added |
| WS1 | Seed registry: Loghub templates, ART seeds, synthetic entity filler, tests | Cloud session `session_016suEmxQMsUKD66MEcF2kow` | `feat/v2-seed-registry` (via PR #3) | Merged (PR #3) | — | 330 seeds (Loghub 322: BGL 120, Linux 118, OpenStack 43, OpenSSH 27, HDFS 14; ART 8), pinned commits + sha256; no IPs in templates (checked). 8 tests collected (session summary said 13). |
| WS2 | v2 rubric | This session | merged to `main` | **Done: frozen 2.4.0** | — | 14 worked examples; 60 rubric tests; 100% line and branch coverage of `data/rubric.py` |
| WS3 | Cohort generator (A/B/B′/C/D), leak lint, leave-one-source-out, stream replay, label-budget subsets | Unassigned | — | Planned (unblocked: rubric frozen) | — (WS1 and WS2 merged) | New files only; target 560 cases (D7) |
| WS4 | Runner/reporter: cohort matrix, CIs, scorecard output | Unassigned | — | Planned | O4 (thresholds); other branch merged | Touches the same files as the other agent. Reporter must auto-add the Loghub citation when the dataset manifest lists Loghub seeds (D8) |
| WS5 | Verify OpenEnv, ATT&CK terms, Zenodo license, alternative telemetry sources | Unassigned | — | Blocked | Hugging Face/Zenodo egress blocked here | Run on Mac or allowlist hosts |
| WS6 | S8 own-data protocol: de-identification, labeling guide, two-labeler agreement | Unassigned | — | Planned | Q7 (real data source) | Must include an adjudication log (disagreements recorded, uncertain cases never silently made gold) and a separate rare high-impact set (S10) |
| WS7 | Chat module: `ingest/chat.py`, thread schema, chat de-identification, synthetic threads, S9 | Unassigned | — | Planned | — (WS2 draft available) | Modular, toggled in config |
| WS8 | Manager boundary: `status --json` preflight + provenance, `generative_managed` adapter (prompt-JSON / grammar / logprob modes), encoder local-path manifest | Unassigned | — | Planned | Mac for final verification | Encoders are not served by the manager |
| WS9 | llamaCPPManager improvements for testing: M0 (pin mcp<2), M1 manifest, M2 local_artifacts, M3 wait/exclusive, M4 memory sampling, M5 offline, M6 test lock, M7 lifecycle-mark, M8/M11 system snapshot; UI U1–U5 deferred | This session | manager branch `feat/benchmark-support` (not pushed: no push access; delivered as patch/bundle) | Done on Linux; pending apply + verification on Mac | Push access or manual apply; Mac checklist in the manager's `docs/BENCHMARK-SUPPORT-TRACKER.md` | Manager suite: 181 passed / 6 failed on Linux (same 6 macOS-only failures as baseline) |

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
| Q5 | Scorecard cost matrix and thresholds | **Decided (D13): start with placeholders** from PRACTICAL_EVAL_V2 §5; revisit after the pilot | WS4 not blocked |
| Q6 | Rubric freeze | **Closed 2026-09-30:** frozen as 2.4.0 (D18), with validity limits recorded | — |
| Q7 | Real data: is there any source of real operational events (logs/alerts, ideally chat threads) from your systems, a lab or a customer that can be de-identified and labeled by two people? Target 200–300 events. If none, results stay synthetic-only and reports say so | Only real data supports a deployment conclusion | WS6, S8/S9 |
| Q8 | Non-served checkpoints (Laya, ModernBERT heads, GLiClass, Von, SemIf): inventory in the manager (M2) or in this repo? | Single source of model provenance | WS8, WS9 |
