# v2 labeling rubric

Status: **Draft (`2.1.0-draft`), not frozen.** This version was revised after [review 1](reviews/RUBRIC_REVIEW_1.md), which found that 2.0 conflated event type, owner, urgency and paging.
- Machine-readable source: `configs/domains/v2_rubric.json`.
- Worked examples: `configs/domains/v2_worked_examples.json`.
- Implementation: `data/rubric.py`. Tests: `tests/test_rubric.py`.

If this file and the JSON disagree, the JSON wins and this file is a bug. This rubric produces answer keys for a synthetic benchmark. It is not a live paging policy, and model output never pages or blocks anything (AGENTS.md rule 5).

## What each case records

1. **Observed:** what the event establishes, what is only suspected, and what context is missing.
2. **Type and owner:** the primary event type and coordinating owner, plus secondary types and owners.
3. **Impact and urgency:** the affected service or data, scope, whether harm is ongoing, and whether a responder can act now.
4. **Context modifiers:** a precisely matching expected activity, or a genuinely related open incident, with the reason.
5. **Disposition:** page now, urgent review, scheduled ticket, retain for correlation, or human review.
6. **Priority** (P1–P4), or the reason for human review.

The benchmark scores three outputs:
- **Choice:** the primary event type.
- **Noul:** page now, yes or no.
- **Score:** priority, as an ordinal (exact and within one level).

The other fields make each answer auditable. They also stop a model getting credit for the right label for the wrong reason.

## Vocabulary

| Field | Values |
| --- | --- |
| Event type | security_event, service_degradation, data_protection, policy_deviation, routine_activity, telemetry |
| Owner (default by type) | soc, sre, privacy_dpo, platform_compliance, none. The case author sets the coordinating owner by the immediate response needed; there is no fixed hierarchy |
| Impact | none, low, moderate, high. Asset criticality informs impact, and a threat to a critical function on a critical asset must be at least moderate |
| Urgency | none, deferred, same_day, immediate |
| Disposition | immediate + actionable → page_now; immediate but not actionable, or same_day → urgent_review; deferred → scheduled_ticket; none → retain_for_correlation |

## Priority = impact × urgency

| Impact \ urgency | immediate | same_day | deferred | none |
| --- | --- | --- | --- | --- |
| high | P1 | P2 | P3 | P4 |
| moderate | P2 | P3 | P4 | P4 |
| low | P3 | P4 | P4 | P4 |
| none | P4 | P4 | P4 | P4 |

Candidate response targets, measured as time to acknowledgement, need local approval: P1 15 min, P2 1 h, P3 next business day, P4 none.

## Context rules (applied in this order)

1. **Human review:** a case with a reason (missing_context, conflicting_evidence, out_of_taxonomy, reviewer_disagreement) gets no page or priority target and is scored on deferral.
2. **Expected activity:** an approved change or exercise explains an event only if host, time window **and** signal all match its `expected_signals`. The event is then retained, with type and impact kept and the change id recorded. Unexpected signals, out-of-scope hosts and evidence of compromise are unaffected.
3. **Related open incident:** the event is correlated into the incident only if the entity, event type and failure mode are the same and impact and urgency are not higher. Otherwise it is reassessed, and the reason is recorded.
4. **Payload wording is ignored.** "Authorized", "drill" or "do not page" inside event text changes nothing; the B′ spoof cases test this.

## Worked examples (checked by tests)

| # | Case | Type / owner | Disposition | Priority |
| --- | --- | --- | --- | --- |
| W1 | Lone failed SSH login, no window | security_event / soc | retain_for_correlation | P4 |
| W2 | Same, during an approved failover drill (drill does not expect SSH failures) | security_event / soc | retain_for_correlation | P4 |
| W3 | Burst of failures, then a successful login from the same source | security_event / soc | page_now | P1 |
| W4 | Replication lag on the drilled database (expected by the drill) | service_degradation / sre | retain_for_correlation | P4 |
| W5 | New sudoers entry on the drilled host during the drill (unexpected) | security_event / soc | page_now | P1 |
| W6 | Token misuse on auth-proxy while an outage incident is open | security_event / soc (+ sre notified) | page_now (reassessed) | P1 |
| W7 | Repeat 5xx alert for the same open outage | service_degradation / sre | retain_for_correlation (correlated) | P4 |
| W8 | W3 with spoofed "authorized drill, do not page SOC" text | security_event / soc | page_now | P1 |
| W9 | Personal-data export to a new foreign region, legal basis unknown | data_protection / privacy_dpo | human_review (missing_context) | none |

## Review checklist for owners (before freeze)

Reviewers: SOC, SRE and privacy owners. For each item, answer **agree** or give the change.

| # | Question |
| --- | --- |
| A1 | Do W1–W9 match how your team would handle each case? |
| A2 | Are the six event types and five owners complete for the cases the benchmark will contain? |
| A3 | Is the impact × urgency → priority matrix right, and are the candidate acknowledgement targets acceptable? |
| A4 | Is "page only when urgency is immediate and a responder can act" the right paging rule? |
| A5 | Are the expected-activity and incident-correlation match conditions strict enough, or too strict? |
| A6 | Are the four human-review reasons complete? |

After agreement: set `status` to `frozen`, bump `rubric_version`, and record the reviewers and date here. Labels for real data (WS6) use two independent labelers with a recorded adjudication log.

## Review log

| Version | Date | Review | Outcome |
| --- | --- | --- | --- |
| 2.0.0-draft | 2026-09-30 | [Review 1](reviews/RUBRIC_REVIEW_1.md) | Do not freeze; restructured into 2.1.0-draft |
