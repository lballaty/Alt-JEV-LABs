# Candidate note: neurosymbolic decision systems (optional)

**Status:** Recorded as a **possible future benchmark family**, by owner request on 2026-10-15 (D37). Not scheduled, not implemented, not measured. No change to the approved S1 baseline, frozen rubric 2.4.0, existing candidate commitments, agent ownership, or current Mac-run priorities.

## Why investigate

Alt-JEV-LABs compares **solutions to a specified decision problem**, not only neural models. A neurosymbolic candidate could combine learned recognition of ambiguous input with explicit logic over trusted facts, relationships, and constraints. The question is empirical: does such a combination reduce consequential error, improve calibration or robustness, or lower latency/memory/labeling cost relative to existing local models, conventional rules, and Jev-style decision interfaces?

A hybrid is not automatically superior. Extra rules can embed incorrect assumptions, suppress genuinely novel signals, add latency, and overfit a synthetic answer key. Pure rules and neural-only models therefore remain necessary controls.

## Candidate families for a later feasibility review

| Arm | Candidate construction | Specific question |
| --- | --- | --- |
| **NS-0: symbolic-only** | Deterministic/logic rules operating only on **structured, trusted context** and observations; explicitly report missing coverage or ambiguous cases | Can explicit rules solve the target task without learning? |
| **NS-1: sequential hybrid** | The **same pinned neural candidate** used in a neural-only arm proposes typed facts and/or a decision; a logic layer reasons over validated facts and records its contribution | What incremental benefit comes from the symbolic stage, holding the neural model constant? |
| **NS-2: integrated neurosymbolic** | A framework that combines probabilistic/neural values with logical inference, possibly differentiably | Does tighter integration improve performance enough to justify complexity? |

Potential open-source technologies to **investigate, not adopt**: [Scallop](https://github.com/scallop-lang/scallop) (probabilistic/differentiable Datalog), [IBM LNN](https://github.com/IBM/LNN) (logical neural networks), and [PyReason](https://github.com/lab-v2/pyreason) (graph and temporal reasoning). Recheck maintenance, license, exact APIs, support on the target Mac, offline operation, and dependency/runtime costs at the feasibility gate. None is asserted to satisfy our JEV-shaped request/response contract without an adapter.

## Compatibility with the existing experiment

- Preserve **S1** as the primary Jev-method baseline and **S0** as separately scoped. Any neurosymbolic run is a **named follow-on candidate/variation** with a frozen scenario ID, not a retroactive change to the original comparison.
- Feed all approaches the **same event and trusted-context evidence**, task questions, and held-out cases. If a symbolic system consumes an additional structured representation, count its extraction, validation, and transformation as part of the **complete measured pipeline**, or report clearly as a separate, non-equivalent arm.
- Implement the **current v2 rubric 2.4.0**: Choice is six-way event type; Noul is page-now probability; Score is **ordinal P1–P4 priority**. Do not silently substitute the older v1 numeric 0–100 Score. A candidate without a defensible probability reports Noul probability and calibration metrics as **N/A**, rather than manufacturing one from a Boolean or rule weight.
- Record **provenance** for neural checkpoints, structured facts, rule/knowledge-base versions, framework/runtime versions, transformation steps, rule firings, and input authority; never conflate a reasoning trace with proof of factual correctness.
- Maintain the separate **deterministic action-authorization/policy boundary**. No symbolic or neural proposal may itself authorize suppression, paging, execution, quarantine, or other governed actions. Statements embedded in untrusted alert payloads cannot supply authorization or trusted context.

## Fair-test design and risks

1. **Isolation / ablation:** compare the same neural checkpoint alone (existing arm), trusted structured rules alone (NS-0), and that checkpoint + the same explicit rules (NS-1). Only then assess NS-2 if local feasibility supports it. Track the changed component for each comparison.
2. **Evaluation:** use existing Choice, Noul and Score criteria; report per-cohort errors, must-page misses, false pages, B-prime spoof robustness, abstention/coverage, calibration where meaningful, p50/p95 complete-pipeline latency, peak memory, energy/resource demand where measured, and implementation/labeling cost.
3. **No answer-key leakage:** the synthetic generator and rubric may already encode many of the same domain rules. A rules-only solution that reproduces those rules is a useful controls check, **not independent evidence of generalization**. Keep a separate independently adjudicated, held-out set with unfamiliar combinations and conflicting facts for any stronger conclusion.
4. **Uncertainty and change:** explicitly test stale/absent trusted facts, contradictory knowledge, out-of-domain input, novel event patterns, ambiguous cases, and rule-version drift; record when the candidate cannot give a supported decision.
5. **Operational constraints:** local-first/offline execution, externally provisioned model checkpoints, no unapproved downloads in runs, source-license review, reproducible graph/rule artifacts, end-to-end timing including reasoning and fact extraction, and target-Mac verification. The lab remains evaluation-only.

## Decision gate before implementation

**No implementation is authorized by this note.** A later owner decision should first choose whether to prioritize this work; identify the candidate family and target framework(s); confirm trusted-context/fact schemas, semantic compatibility, licensing and Mac feasibility; assign ownership; and approve independent evaluation evidence and acceptance metrics. If those gates cannot be satisfied, leave this as a documented possibility.

See [TRACKER.md](TRACKER.md) (D37) and [TEST_SCENARIOS.md](TEST_SCENARIOS.md) for the existing S0/S1 experiment and variations.
