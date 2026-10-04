# v2 evaluation tracker

Last updated: 2026-10-04 (reference-only seed sources D28; WS4 v2 runner, report and scorecard implemented and tested on Linux with stubs, no model result, Mac gates open; PR #17 intent reconciled; WS3/WS7 implementation updates preserved; WS10 evidence audit; WS9 bundle verified; Mac/target-stream gates open). **Update this file in every PR that changes plan, intent or status.** Nothing in the v2 plan has been measured yet. Status values: `Not started` · `Planned` · `In progress` · `Blocked` · `Ready for review` · `Merged`.

## Intent

Build a reusable, local-first way to compare viable solutions for a concrete decision use case and choose the best fit under stated requirements. Each use case supplies a decision contract and rubric, representative and adversarial cases, candidate approaches and simple baselines, failure costs, operational constraints and acceptance criteria. The result is a comparative scorecard: screen hard requirements first, show consequential errors and operational trade-offs for feasible candidates, and explain the recommendation or why evidence is insufficient. Performance estimates apply only under the tested conditions. The scorecard supports a named human decision owner, who records whether the combined evidence and residual risk justify a specified pilot or deployment; a test pass is not an automatic certification or release decision.

The first reference use case is an operational triage gateway in front of SOC/SRE and privacy workflows. Its v2 evaluation ranks candidates on offline operation, correct event classification and priority, must-page recall, resistance to spoofed authorization, labeling cost, latency and throughput on the target Mac. A separate proposed gateway would handle live ingress, policy enforcement and dispatch; this repository is the evaluation harness. Classifier output never authorizes an action (AGENTS.md rule 5). See [project intent and adaptation](PROJECT_INTENT.md).

Plan documents:

| Doc | Branch | Purpose |
| --- | --- | --- |
| `docs/BLUEPRINT_V2.md` | `main` (PR #1) | v2 protocol, candidate matrix, training/calibration, timing |
| `docs/DATASET_PLAN_V2.md` | `main` | Seed sources, license review, cohorts, split and leakage rules, workstreams |
| `docs/PRACTICAL_EVAL_V2.md` | `main` | Selection-oriented suites S1–S9, event+context format, chat module, scorecard |
| `docs/PROJECT_INTENT.md` | `main` (PR #17) | Reusable comparison framework, reference triage use case, implementation boundary |
| `docs/OWNERSHIP.md` | `main` | Who owns which files/workstreams; working rules incl. auto-merge (D21) |
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
| D20 | 2026-10-01 | Add a small generative arm (Gemma family, ~270M and ~1B, alongside the existing Gemma 4 E2B entry) to test the smallest viable local LLM. Served through llamaCPPManager like the other generative arms; checkpoints pinned from the Mac inventory. A fine-tuned checkpoint (e.g. `gemma-270m-compliance-mlx`) is reported as a separate arm with its training data disclosed. **Amended 2026-10-01:** `gemma-270m-compliance-mlx` is excluded from the alert-triage use case because it was tuned for compliance questions; it is reserved for a future compliance-domain use case | BLUEPRINT_V2 candidate matrix |
| D21 | 2026-10-04 | Standing owner instruction: agents merge to `main` automatically and update this tracker in the same change, without waiting for review, because agents see only GitHub. Overrides `AGENTS.md` rule 6 for ordinary work; tests must pass first; guardrails in OWNERSHIP.md rule 3 still apply. Revocable by the owner | `docs/OWNERSHIP.md` |

| D22 | 2026-10-04 | Owner requested repository-visible acknowledgement and an agent ID. This ebook/companion session identifies as `codex-ebook-companion-01` and acknowledges AGENTS.md, OWNERSHIP.md, TRACKER.md and D21. Scope: ebook publishing and companion coordination; no implementation workstream claimed or reassigned | Libor's instruction in ebook session, 2026-10-04; `docs/OWNERSHIP.md` acknowledgement |
| D23 | 2026-10-04 | Owner asked each agent to take an ID in the shared instructions. The cloud session that built WS1 and launched the WS3/WS7 subagents is `claude-cloud-ws1-01`; IDs are listed in `docs/OWNERSHIP.md` under Agent IDs | Libor's instruction, 2026-10-04; `docs/OWNERSHIP.md` |
| D24 | 2026-10-04 | Only two agents exist: `claude-cloud-ws1-01` (implementation) and `codex-ebook-companion-01` (ebook/companion). References to a calibration agent, planning agent, 'other agent' or 'this session' in older rows are earlier ended sessions, not active agents. WS4, WS8, WS9, WS10 are unassigned; `docs/OWNERSHIP.md` updated | Libor's instruction, 2026-10-04 |

| D25 | 2026-10-04 | Owner asked `codex-ebook-companion-01` to take prior calibration/planning work only where non-conflicting. Latest D24 ownership gives implementation files to Claude; calibration/code/WS4 remain there. Codex takes planning docs/tracker maintenance, manager docs/WS9 handoff coordination and WS10 research. Blueprint and frozen rubric remain Claude's. Preserve PR #17 and existing branches/bundles; hardware/evidence gates unchanged | Libor's instruction in ebook session, 2026-10-04; `docs/OWNERSHIP.md` |
| D26 | 2026-10-04 | Real operational events (Q7) are **optional guidance** for anyone using the framework, not a requirement of this project. The project proceeds with the data available now (Loghub templates, Atomic Red Team seeds, generator-authored cases). Reports state results are synthetic-only and do not support a deployment conclusion. Real-data intake and de-identification tooling (former WS6) are not built | Libor's instruction, 2026-10-04; `docs/REAL_DATA_GUIDE.md` |
| D27 | 2026-10-04 | Handoff to the Mac agent (Codex): `docs/HANDOFF_MAC.md`. WS8 and the `models/*`/`training/*` retarget released from `claude-cloud-ws1-01` to the Mac agent. Mac agent ID chosen by that agent and registered in OWNERSHIP.md | Libor's instruction, 2026-10-04; `docs/HANDOFF_MAC.md` |
| D28 | 2026-10-04 | Reference-only seed sources (option A). Any seed source whose license does not clearly allow us to publish its content is **not committed**. We publish only a reference (URL, pinned commit, exact file paths, expected sha256, license, format, extractor) in `data/seeds/references.json`; users fetch and derive a git-ignored local registry with `data/seed_references.py`. Derived registries and datasets built from them are never published. Already-committed sources (Loghub templates, Atomic Red Team) are unchanged. SecRepo, OpenEnv, ATT&CK and Zenodo stay excluded as unverified | Libor's instruction, 2026-10-04; `docs/SEED_REFERENCES.md` |

## Open decisions

All open owner decisions are consolidated under **Open questions** at the end of this file. The former O3 is now Q7 and O4 is now Q4/Q5.

## Workstreams

| WS | Scope | Owner | Branch | Status | Blocked by | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| — | Finite JSON decoding, validation calibration, v2 blueprint | Other agent | `feat/finite-json-calibration` | Merged (PR #1) | — | Six routes applied to BLUEPRINT_V2 on the plan branch |
| — | Dataset + practical eval plan, this tracker | This session | `plan/v2-datasets-test-structure` | Merged (PR #2) | — | main merged in; README license + Loghub credits added |
| WS1 | Seed registry: Loghub templates, ART seeds, synthetic entity filler, tests | Cloud session `session_016suEmxQMsUKD66MEcF2kow` | `feat/v2-seed-registry` (via PR #3) | Merged (PR #3) | — | 330 seeds (Loghub 322: BGL 120, Linux 118, OpenStack 43, OpenSSH 27, HDFS 14; ART 8), pinned commits + sha256; no IPs in templates (checked). 8 tests collected (session summary said 13). |
| WS2 | v2 rubric | This session | merged to `main` | **Done: frozen 2.4.0** | — | 14 worked examples; 60 rubric tests; 100% line and branch coverage of `data/rubric.py` |
| WS3 | Cohort generator (A/B/B′/C/D), leak lint, leave-one-source-out, stream replay, label-budget subsets | Cloud session `session_016suEmxQMsUKD66MEcF2kow` | `feat/ws3-cohort-generator` | Cohorts, grouped split, manifest and leak lint merged under D21 once tests pass; **leave-one-source-out, stream replay (S6) and label-budget subsets (S7) not yet built** | — (WS1 and WS2 merged) | Added `data/generator_v2.py`, `tests/test_generator_v2.py`, `docs/GENERATOR_V2.md`. 560 cases (A 200, B 125, B′ 60, C 100, D 75), seed 42, labels only from rubric 2.4.0, cohort D unlabeled (`needs_adjudication`). Verified on Linux: lint-clean and byte-identical for the same seed (also across PYTHONHASHSEED); manifest hashes match files. Generated data is synthetic and git-ignored. 294 of 560 cases use generator-authored seeds (disclosed in the manifest); archetype evidence is single-author, unreviewed by SOC/SRE/DPO; cohort B is service events only. See GENERATOR_V2.md review flags |
| WS4 | Runner/reporter: cohort matrix, CIs, scorecard output | `claude-cloud-ws1-01` | `feat/ws4-v2-report` | Implemented and tested on Linux with stub candidates; merged under D21 once tests pass. Full suite 265 passed (151 existing + 114 new); v1 path and tests unchanged. **Not verified:** any MLX/MPS/Laya/generative run, memory sampling, latency on the M4 Max, offline behaviour of real adapters. **No v2 model result exists.** The only model-shaped run was a lexical BM25 plumbing check on synthetic data, not recorded as evidence | **Q4** for the p95 latency budget (`p95_ms_max` is null, so the gate shows "not evaluated", never pass); memory cap/reserve (D12) and cost matrix (D13) are placeholders; Mac for target-hardware gates | Added `evaluation/{v2_data,v2_metrics,v2_runner,scorecard,v2_report,v2_cli}.py`, `configs/selection_scorecard.yaml`, `docs/EVALUATION_V2.md`, `tests/test_v2_*.py`. Loader verifies the manifest with the generator's own check (fails loudly); cohort matrix with Wilson and seeded group-cluster bootstrap; cohort D never gets accuracy/ECE; pooled calibration with validation-fit temperature; scorecard states pass/fail/inconclusive/not evaluated and a recommended/not recommended/insufficient evidence verdict (a pass is not deployment approval); synthetic banner and automatic Loghub citation (D8). Not built: S4-S7, explainability, ops fit, S9 runner, abstain output. Models/training not edited (released to the Mac agent, D27); retargeting needs are in `docs/EVALUATION_V2.md`. Review flags there (small n makes most gates inconclusive; signal-name shortcut; spoof threshold 0.95 borrowed from the chat module) |
| WS5 | Verify OpenEnv, ATT&CK terms, Zenodo license, alternative telemetry sources | `claude-cloud-ws1-01` | `feat/seed-references` | In progress: GitHub-hosted licenses verified (`docs/SEED_SOURCE_LICENSES.md`); SecRepo, OpenEnv, ATT&CK, Zenodo still unverified. **Reference-only seeds (D28) merged under D21:** Logstash patterns (Apache-2.0), Vector (MPL-2.0) and Wazuh (GPL-2.0) are listed in `data/seeds/references.json` with pinned shas and file hashes; nothing from them is committed | Hugging Face/Zenodo egress blocked here | Run on Mac or allowlist hosts. Added `data/seed_references.py` (fetch/verify/build), `data/seeds/references.json`, `docs/SEED_REFERENCES.md`, `tests/test_seed_references.py`. Real fetch/verify/build run on Linux: 40 local-only templates (Logstash 27, Vector 3, Wazuh 10); no IPs in any template. **Not done:** archetypes do not use local templates (hard-coded ids in `generator_v2.py`); generator manifest lacks `contains_local_only_seed_text`; scrubbing of names/hosts is best effort; Wazuh pin has no ruleset XML, Vector yield is small |
| WS6 | Real-data guidance (optional, D26): `docs/REAL_DATA_GUIDE.md`. Intake loader, log de-identification and adjudication tooling not built | `claude-cloud-ws1-01` | — | Guidance merged; tooling **Not started (optional)** | — (no longer blocked on Q7) | Must include an adjudication log (disagreements recorded, uncertain cases never silently made gold) and a separate rare high-impact set (S10) |
| WS7 | Chat module: `ingest/chat.py`, thread schema, chat de-identification, synthetic threads, S9 | `claude-cloud-ws1-01` (cloud session `session_016suEmxQMsUKD66MEcF2kow`) | `feat/ws7-chat-module` | Ready for review (merged under D21 once tests pass) | — (WS2 frozen) | Off by default (`configs/chat_module.json`). Added `ingest/__init__.py`, `ingest/chat.py`, `tests/test_chat_ingest.py` (30 tests), `docs/CHAT_MODULE.md`; no existing code touched. Verified on Linux: full suite 105 passed (75 + 30), synthetic sentinels fully removed by de-identification, deterministic output. **Not verified:** de-identification recall on real chat (none used), any S9 model result, S9 runner registration (WS4). Chat claims are flagged, never authorization (D4). Review flags in `docs/CHAT_MODULE.md` |
| WS8 | Manager boundary: `status --json` preflight + provenance, `generative_managed` adapter (prompt-JSON / grammar / logprob modes), encoder local-path manifest | Released to the Mac agent (claim by ID in the PR that starts it); `claude-cloud-ws1-01` will not edit `models/*` or `training/*` meanwhile | — | Planned | Mac for final verification | Encoders are not served by the manager |
| WS9 | llamaCPPManager improvements for testing: M0 (pin mcp<2), M1 manifest, M2 local_artifacts, M3 wait/exclusive, M4 memory sampling, M5 offline, M6 test lock, M7 lifecycle-mark, M8/M11 system snapshot; UI U1–U5 deferred | codex-ebook-companion-01 | archived delivery on manager main; application pending | Blocked (Mac application/validation; delivery verified) | Mac host, manager file claims and H2–H5 | 2026-10-04: archive SHA-256, member inventory, bundle tip/prerequisite and patch headers verified. No applied benchmark branch/tracker found. Historical Linux results retained; live CLI/MLX/GUI checks not run. See MANAGER_HANDOFF.md. |
| WS10 | Realism grounding: make the synthetic tests match published evidence on real alert streams. Research sources (industry SOC/SRE surveys, public incident reports and postmortems, academic log/alert datasets) for class mix and base rates, alert volumes and false-positive rates, burst and correlation patterns, message formats and noise. Set generator parameters from them with citations. Add a realism check: compare generated distributions with the cited figures, and have a practitioner rate a blind sample of generated vs real-looking cases | codex-ebook-companion-01 | this PR → main | In progress (source audit complete; validation open) | Artifact license clarification, independent count reproduction, practitioner assessment and target-stream evidence | 2026-10-04: read Microsoft/Omdia summary, USENIX paper, Zhao bank study and PagerDuty primary report; corrected denominator/prevalence claims. Pinned four dataset candidates and flagged license conflicts; no imports. REALISM_RESEARCH.md / REALISM_DATASETS.md. Web retrieval works here; shell/model egress not established. |

## Planning successor queue

Owner: `codex-ebook-companion-01` (D25).

- PR #17 reconciled with current main in this change: reusable evaluation intent preserved; WS3/WS7 status updated without changing implementation or the frozen rubric.
- Realism branch inventoried: behind main, no unique commits/content requiring import. Manager bundle inventoried and checksum verified; Mac application/validation remains open.
- Coordinate with Claude's WS3/WS7 work through GitHub; calibration/code/WS4 and blueprint/rubric remain Claude's scope.
- No new measurement, implementation completion or Mac verification is implied by this handover.

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
| Synthetic tests unlike real alert streams (wrong base rates, too clean, too balanced), so rankings don't transfer | WS10 research-grounded parameters with citations; realism check; S6 stream at realistic prevalence; S8 real data remains the decisive check |
| Public evidence has incompatible denominators and does not establish target-stream prevalence | Use source-backed case designs and explicitly assumed sensitivity profiles; obtain independent labels and practitioner validation before deployment claims |
| Parallel agents editing the same files | WS1–WS3, WS7 add new files only; WS4 waits for the other branch to merge |

## Handoff: continue on the M4 Mac

See `docs/HANDOFF_MAC.md` (written 2026-10-04): current state, in-flight PRs, released ownership (WS8 and the `models/*`/`training/*` retarget), Mac steps, owner questions and work order.

## Open questions (owner: Libor)

| # | Question | Why it matters | Blocks |
| --- | --- | --- | --- |
| Q1 | Which llamaCPPManager model names/ports are the generative candidates? Include the small Gemma arm (D20): which base (not fine-tuned) Gemma sizes and quantizations are installed? | Defines the served generative arms | WS8 |
| Q2 | `HF_HUB_OFFLINE=1` permanently on the MLX entries, or a benchmark-only group/profile? | Prevents downloads during runs | WS8 |
| Q3 | Which encoder/classifier candidates to include (Laya English 421M vs multilingual 322M, Von, GLiClass, SemIf, ModernBERT heads, Gemma LoRA)? Where are they stored locally? | The manager does not serve these; they need a local-path manifest | WS8, candidate matrix |
| Q4 | p95 latency budget; confirm memory cap 96 GB / reserve 16 GB (D12) | Sets the remaining scorecard hard gate | WS4 |
| Q5 | Scorecard cost matrix and thresholds | **Decided (D13): start with placeholders** from PRACTICAL_EVAL_V2 §5; revisit after the pilot | WS4 not blocked |
| Q6 | Rubric freeze | **Closed 2026-09-30:** frozen as 2.4.0 (D18), with validity limits recorded | — |
| Q7 | Real operational events: **decided D26 (2026-10-04): optional.** Not required by the project; guidance for framework users is in `docs/REAL_DATA_GUIDE.md`. Results stay synthetic-only and reports say so | Only real data supports a deployment conclusion | — (no longer blocks WS6, S8/S9) |
| Q8 | Non-served checkpoints (Laya, ModernBERT heads, GLiClass, Von, SemIf): inventory in the manager (M2) or in this repo? | Single source of model provenance | WS8, WS9 |

| Q9 | Realism sources: internal or customer figures? | **Answered 2026-09-30: none available.** Realism rests on public evidence only (WS10) | — |
