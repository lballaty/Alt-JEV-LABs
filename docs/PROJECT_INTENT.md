# Alt-JEV-LABs Project Intent

## Purpose

Alt-JEV-LABs develops a repeatable way to compare possible solutions for a concrete decision workflow and choose the best fit for its use case. A project should define the decision, compare rules, retrieval, specialized and generative models, and relevant combinations, test each viable solution with its independent controls, and publish the evidence and limits needed for a product decision. The lab is intended to support more than one use case. It does not assume that a model must win or that every decision needs an LLM.

For each use case, distinguish three questions:

1. **Can the decision be expressed and tested?** Specify inputs, trusted context, outputs, a versioned rubric, ambiguous cases and failure costs.
2. **Which solution fits best?** Compare viable approaches on the same ordinary, adversarial and shifted cases, using the same decision contract. Measure consequential errors, coverage and abstention, latency, resource and labeling needs, operating cost, and behavior under the required controls.
3. **Can the proposed system operate within its controls?** Test the model's proposal alongside the independent policy boundary, routing and failure behavior. Measure the complete path when the use case requires live operation.

A favorable synthetic score demonstrates behavior on those constructed cases. It does not prove future accuracy or operational readiness. Real, independently labeled cases from the intended environment and a monitored pilot are needed to support a deployment decision. Reports should show each feasible candidate against use-case requirements, including missed consequential events, false actions, coverage, latency, resource and labeling needs, uncertainty, provenance and the conditions under which the result applies. State which candidates fail hard requirements, then explain any recommended choice and the trade-offs among the remaining options. If evidence is insufficient or no candidate qualifies, report that explicitly. A recommendation estimates likely performance under the tested conditions; it is not a guarantee.

## First reference use case: operational alert triage

The first evaluation concerns a proposed **Intent-Governed Triage Gateway**. Its runtime architecture is a separate product concept:

1. An ingress service receives alerts and assembles trusted context, such as approved change scope, open incidents, asset records and data-transfer registers.
2. A local model proposes event type, owner, priority, notification, missing facts and possible responder actions. It cannot call dispatch or remediation systems.
3. A deterministic policy kernel checks independently verifiable conditions before notification or suppression, preserves an auditable decision, and escalates deadlines to accountable responders. Dispatch and any remediation are governed separately.

The gateway could connect monitoring and security feeds to on-call and business-hours workflows. Existing source-side grouping or silencing must be accounted for to avoid conflicting decisions. The runtime gateway, its integrations and any guide or playbook are not implemented by this repository.

For this use case, the lab evaluates the model's semantic triage, the effect of trusted context, spoofed claims inside alerts, duplicate-incident handling and priority preservation. System-level tests should also cover source-defined critical paths, dispatch failures, retries, idempotency, escalation and the policy kernel. The model's inability to call a paging API is enforceable by architecture; no benchmark can guarantee that every critical event is detected. An elapsed deadline requires a recorded human containment decision, not automatic isolation solely because a fact remains unverified.

The [frozen v2 alert-triage rubric](RUBRIC_V2.md) and its worked examples are the first domain-specific answer key. They are benchmark labels, not a live paging policy. The [practical evaluation plan](PRACTICAL_EVAL_V2.md) defines the proposed suites and scorecard.

## Adapting the framework to another use case

A new project should provide:

- **Decision contract:** the questions, output types, downstream consumers and actions that remain outside model authority.
- **Domain rubric:** versioned labels, priority or score meaning, contextual exceptions, uncertainty and adjudication rules.
- **Evidence:** representative and difficult cases, provenance and usage rights, independent labels where possible, and split groups that prevent related cases from leaking across train and test.
- **Comparisons:** viable solution classes, including a simple baseline, candidate models where appropriate, supported capabilities and a common measurement protocol.
- **Acceptance criteria:** hard constraints and weighted preferences for consequential error costs, coverage, calibration where probabilities are used, latency, memory, labeling and operating cost, offline behavior and operational failure paths.
- **System boundary:** deterministic checks and human oversight appropriate to that project's actions, tested separately from model accuracy.

These are design requirements for a reusable framework, not a claim that the present code has a general use-case plug-in interface. Domain-specific code and adapters are expected until such an interface is implemented and tested.

## Current implementation boundary

The repository currently has a v1 synthetic smoke-test harness with four model routes; Mac model runs require local checkpoints. For the first v2 use case, the pinned seed registry and rubric 2.4.0 are merged, while WS3 cohort generation, the full report matrix and Mac model measurements are not complete. No v2 or Apple Silicon performance result is claimed. The [tracker](TRACKER.md) is the current status and decisions record; [README](../README.md) distinguishes the runnable v1 commands from v2 plans.

The code is Apache-2.0 and documentation is CC BY 4.0. Third-party seeds keep their own terms; review [the dataset plan](DATASET_PLAN_V2.md) and [NOTICE](../NOTICE) before reusing those records in another project.
