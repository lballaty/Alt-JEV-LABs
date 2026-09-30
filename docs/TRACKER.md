# v2 evaluation tracker

Last updated: 2026-09-30. **Update this file in every PR that changes plan, intent or status.** Nothing in the v2 plan has been measured yet. Status values: `Not started` · `Planned` · `In progress` · `Blocked` · `Ready for review` · `Merged`.

## Intent

Build a practical, reproducible evaluation for choosing a local decision model to put in front of SOC/SRE queues. It must rank candidates on offline operation, correct routing, must-page recall, resistance to spoofed authorization, labeling cost, latency and throughput on the target Mac. The output is a selection scorecard, not a showcase for one model. Classifier output never authorizes an action (AGENTS.md rule 5).

Plan documents:

| Doc | Branch | Purpose |
| --- | --- | --- |
| `docs/BLUEPRINT_V2.md` | `main` (PR #1) | v2 protocol, candidate matrix, training/calibration, timing |
| `docs/DATASET_PLAN_V2.md` | `plan/v2-datasets-test-structure` | Seed sources, license review, cohorts, split and leakage rules, workstreams |
| `docs/PRACTICAL_EVAL_V2.md` | `plan/v2-datasets-test-structure` | Selection-oriented suites S1–S9, event+context format, chat module, scorecard |

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

## Open decisions (owner: Libor)

| # | Question | Options | Blocks |
| --- | --- | --- | --- |
| O3 | Own real data for S8 (200–300 events) and S9 (chat threads) | Source, de-identification owner | Deployment-grade conclusion |
| O4 | Scorecard thresholds, cost matrix, latency/memory budgets | Placeholder values in PRACTICAL_EVAL_V2 §5 | WS4 scorecard |

## Workstreams

| WS | Scope | Owner | Branch | Status | Blocked by | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| — | Finite JSON decoding, validation calibration, v2 blueprint | Other agent | `feat/finite-json-calibration` | Merged (PR #1) | — | Six routes applied to BLUEPRINT_V2 on the plan branch |
| — | Dataset + practical eval plan, this tracker | This session | `plan/v2-datasets-test-structure` | Ready for review | — | main merged in; README license + Loghub credits added |
| WS1 | Seed registry: Loghub templates, ART seeds, synthetic entity filler, tests | Cloud session `session_016suEmxQMsUKD66MEcF2kow` | `feat/v2-seed-registry` | In progress | — | `data/seeds/LOGHUB_LICENSE` now exists on the plan branch; WS1 must keep it and not overwrite it with different text |
| WS2 | v2 rubric: 6 routes, precedence, page policy, P1–P4 anchors, `needs_human`, context schema | Unassigned | — | Planned | — | Unblocked by D2 |
| WS3 | Cohort generator (A/B/B′/C/D), leak lint, leave-one-source-out, stream replay, label-budget subsets | Unassigned | — | Planned | WS1, WS2 | New files only; target 560 cases (D7) |
| WS4 | Runner/reporter: cohort matrix, CIs, scorecard output | Unassigned | — | Planned | O4 (thresholds); other branch merged | Touches the same files as the other agent. Reporter must auto-add the Loghub citation when the dataset manifest lists Loghub seeds (D8) |
| WS5 | Verify OpenEnv, ATT&CK terms, Zenodo license, alternative telemetry sources | Unassigned | — | Blocked | Hugging Face/Zenodo egress blocked here | Run on Mac or allowlist hosts |
| WS6 | S8 own-data protocol: de-identification, labeling guide, two-labeler agreement | Unassigned | — | Planned | O3 | |
| WS7 | Chat module: `ingest/chat.py`, thread schema, chat de-identification, synthetic threads, S9 | Unassigned | — | Planned | WS2 | Modular, toggled in config |

## Verified vs not verified

| Item | Status |
| --- | --- |
| v1 harness tests (5/5) and lexical-only smoke run on Linux | ✅ Verified 2026-09-30 |
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
| Parallel agents editing the same files | WS1–WS3, WS7 add new files only; WS4 waits for the other branch to merge |
