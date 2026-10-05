# Test scenarios: a baseline aligned with published Jev testing, plus variations

Status: **structure adopted by the owner (D36, 2026-10-05); nothing implemented yet.** Written by `claude-cloud-ws1-01`. Items marked **proposed** still need owner confirmation. Sources for every claim about Jev and its published testing are in `docs/JEV_SOURCES.md`.

## 1. Why scenarios

We want two things at once: (a) a test that follows how Jev has been tested in published work, so results are comparable in method; and (b) our own variations (spoofed text, trusted context, thresholds, and so on), which matter for real alert triage and other use cases. A **scenario** is a named, versioned configuration of the same harness. The baseline scenarios fix the published method; each variation changes one thing relative to a baseline, so its effect can be isolated.

TypeSafe has not published its own test protocol. The best-documented method is the independent 37-dataset evaluation (arXiv 2609.37647, code MIT), supported by the agent-security evaluation (arXiv 2609.33401) and TypeSafe's official SDKs and guidance. "Published method" below means those sources.

## 2. Baseline scenarios

### S0 — replication anchor (public datasets)

- **What:** run the local alternatives on a subset of the 37-dataset paper's public datasets, with that paper's frozen templates and its released harness, and compare with the paper's **published** Jev results (cited, not rerun; D31).
- **Why:** the only way in phase 1 to compare alternatives with Jev on accuracy and calibration, using identical requests, without calling Jev.
- **Dataset subset (proposed, needs owner confirmation):** the sets closest to triage: intent routing (Banking77, CLINC150), prompt-injection detection, moderation (OpenAI moderation set, ToxicChat), grounding (LLM-AggreFact), plus one plain classification control (AG News). Final list after checking each dataset's license and size on the Mac.
- **Caveats to report with every S0 result:** public data may be in some models' training data (the paper's own caution); latency differs by hardware and network (D32); the paper's templates were written for Jev, not tuned for other models.
- **Preparation:** datasets are downloaded once as an explicit preparation step on the Mac, never during a timed run, never committed; each dataset's license is respected.

### S1 — Jev method on our task (alert triage) — **the primary result**

Our synthetic alert-triage cases (rubric 2.4.0, cohort generator), asked the way Jev is asked:

| Aspect | S1 setting |
| --- | --- |
| Request | One canonical Jev-shaped request per case: `state` = the event plus the trusted-context block; named typed questions |
| Event type | Choice over the six types, each with a one-sentence description taken from the rubric |
| Page now | Noul ("Does this event require paging the on-call human now?") |
| Priority | Score with four described levels, P1-P4, taken from the rubric |
| Questions per call | All three in one request (Jev's native mode) |
| Generative models | Option probabilities from one forward pass, one token per option, no text generation (the 37-dataset paper's method) |
| Templates | One frozen template, piloted on non-test cases only |
| Threshold | Fixed 0.5 for Noul, as published |
| Metrics | Accuracy and F1 with bootstrap intervals; AUROC and AUPRC; ECE at 15 bins (10 bins also shown); Brier; accuracy at 80% and 50% coverage ranked by confidence; risk-coverage curve |
| Latency | Client-side end-to-end, as published, plus the D32 network-path label |
| Versions | Every model and checkpoint revision pinned; the returned model/version recorded per call |

All candidates (local servers that speak Jev's format, Laya-MLX through a thin wrapper, generative models through the option-probability readout) receive the identical request. A later hosted Jev run (phase 2, if approved) is then only a configuration change: the official SDK sends the same request to the cloud endpoint.

## 3. Variations (follow-on scenarios)

Each variation changes one setting relative to S1 (or S0 where noted) and is reported as a difference from its baseline.

| ID | Changes | Tests | Relevant to |
| --- | --- | --- | --- |
| V-threshold | Noul threshold tuned on validation | Fair operating point (published work shows 0.5 is often poor) | Any yes/no decision |
| V-band | Allow / escalate / block band with error budgets | How much can be automated safely | Deciding what to auto-route |
| V-separate | One request per question | Question isolation, cost and latency | Integration design |
| V-labels, V-rename | Bare labels; renamed or obscured option names with definitions kept | Whether a model reads definitions or names | Any taxonomy |
| V-context | Trusted-context block removed | Effect of context (one study saw recall 74.9% to 95.1%) | Change windows, ownership |
| V-spoof | Cohort B' (claims of authorisation inside alert text); held-out wrapper families | Resistance to spoofed text | Security; any untrusted input |
| V-negation, V-jargon | Cohorts B and C | Wording robustness | Teams with house slang |
| V-boundary | Cohort D (abstention, never gold-labelled) | Behaviour on genuinely ambiguous events | Human-in-the-loop design |
| V-signal-hidden | `event.signal` removed from the state | Validity (the field nearly names the type) | Every result |
| V-jagged | Date, counting and long-noisy-input controls (vendor-documented weaknesses) | Known weak spots | Timestamped, bursty logs |
| V-json, V-grammar | Generative models write JSON, free or grammar-constrained | How chat models are usually deployed; schema failures | Teams using chat models |
| V-scale | Priority as 0-100 urgency, then binned | Models without a Score primitive | Compatibility |
| V-label-budget, V-LOSO, V-stream | Few labelled examples; leave-one-source-out; stream replay | Adapting to a new organisation | New deployments |
| V-chat | Chat-thread input (S9) | Chat-based triage | Slack/Teams workflows |
| V-gates | Our scorecard: must-page and false-page gates, cost matrix, cohort matrix | Operational fitness | Deployment decisions (still not approval) |

## 4. How scenarios are run (design, proposed details)

- A scenario file (one per scenario, versioned) names: dataset (S0 public subset or our cohorts), request-builder options (described or bare options, combined or separate questions, context on or off, signal shown or hidden), threshold policy, metric set, and the baseline it varies.
- One runner reads a scenario; every report states the scenario id, its baseline, the single difference, data kind (synthetic, public, or real), and full provenance.
- Order of work: (1) S1 request builder and metrics; (2) S0 using the 37-dataset harness (read its template and scoring code at implementation time); (3) variations one setting at a time.

## 5. Ownership and dependencies

| Work | Files | Owner | Depends on |
| --- | --- | --- | --- |
| S1 request builder, scenario files, new metrics, network-path field | `evaluation/*`, `data/` (new files) | `claude-cloud-ws1-01` | — |
| Adapters accept the canonical request; option-probability readout for generative models; revision pinning | `models/*` | Mac agent (WS8, D27) | S1 request format |
| S0 dataset preparation and runs | new files; data kept local | Mac agent with `claude-cloud-ws1-01` | Dataset subset confirmed; Mac |
| Hosted Jev configuration | adapter using the official SDK | not started | Phase 2 approval (D31), terms check, key, spend limit |

## 6. Not needed

No further reading on methodology. At implementation time only: the 37-dataset harness's template and scoring code (MIT, reachable), and TypeSafe's customer terms before any hosted run.
