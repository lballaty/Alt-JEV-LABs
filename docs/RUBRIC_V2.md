# v2 labeling rubric

Status: **Draft (`2.2.0-draft`), not frozen.** Revised after [review 1](reviews/RUBRIC_REVIEW_1.md) and [review 2](reviews/RUBRIC_REVIEW_2.md).
- Machine-readable source: `configs/domains/v2_rubric.json`.
- Worked examples: `configs/domains/v2_worked_examples.json`.
- Implementation: `data/rubric.py`. Tests: `tests/test_rubric.py`.

If this file and the JSON disagree, the JSON wins and this file is a bug. The rubric produces answer keys for a synthetic benchmark. It is not a live paging policy, and model output never pages or blocks anything (AGENTS.md rule 5).

## Core principles

1. **Priority describes the condition; notification is a separate decision.** Explaining an alert by a change, or attaching it to an open incident, suppresses the notification only. An attached repeat keeps the incident's priority.
2. **Priority is a response class.** The classes are defined first, then mapped consistently to targets.
3. **Uncertainty is time-bound.** A provisional label has a reason, the missing facts, a triage owner and a deadline. Possible ongoing harm still pages.
4. **Claims inside logs are untrusted; observations are evidence.** Trusted context is the change calendar and approved test scope, the incident register, asset records and identity records.

## Decision order

1. Record what was observed. Separate observed facts from source-supplied labels and authorization claims.
2. Identify the event type and coordinating owner, plus any secondary owners.
3. Assess impact, urgency and missing facts. An unknown fact makes the label provisional, with a triage owner and deadline.
4. Apply a narrowly matched change explanation: host, time window, expected signal, and impact within that signal's bound. It may suppress the notification. It never erases the event or overrides evidence of compromise.
5. Correlate with an open incident. An exact repeat (same entity, type and failure mode, no worse) attaches with no new notification and keeps the incident's priority. New behavior is reassessed.
6. Decide the notification. Page for an immediate action a responder can take; otherwise urgent or scheduled review within the priority's target.

## Response classes (priority)

| Priority | Meaning | Candidate acknowledgement target |
| --- | --- | --- |
| P1 | Immediate response, high impact | 15 minutes |
| P2 | Immediate response, low or moderate impact | 1 hour |
| P3 | Response the same business day | end of business day |
| P4 | Scheduled work, or retained with no response | next business day, or none if retained |

| Impact \ urgency | Immediate | Same day | Deferred | None |
| --- | --- | --- | --- | --- |
| High | P1 | P3 | P4 | P4 |
| Moderate | P2 | P3 | P4 | P4 |
| Low | P2 | P3 | P4 | P4 |
| None | invalid | invalid | invalid | P4 |

Notification: immediate and actionable → page now; immediate but not actionable, or same day → urgent review; deferred → scheduled review; none → no notification. Every paged event is P1 or P2.

Provisional triage deadlines: P1 1 hour, P2 4 hours, P3 end of business day, P4 2 business days. Reasons: missing context, conflicting evidence, outside the taxonomy, reviewer disagreement.

## Vocabulary

| Field | Values |
| --- | --- |
| Event type | security_event, service_degradation, data_protection, policy_deviation, routine_activity, telemetry |
| Owner | soc, sre, privacy_dpo, platform_compliance. Routine activity and telemetry have no receiving team. The owner of a retained security event owns correlation, not a ticket per event |
| Handling | new, explained_by_change, attached_to_incident |

## Worked examples (checked by tests)

| # | Case | Type / owner | Notification | Priority | Handling |
| --- | --- | --- | --- | --- | --- |
| W1 | Lone failed SSH login | security / SOC | none | P4 | new (retained) |
| W2 | Same, during an unrelated drill | security / SOC | none | P4 | new (drill has no effect) |
| W3 | 42 failures then success, same source | security / SOC | page | P2 provisional, 4 h | new |
| W4 | Drill replication lag within bound, primary serving | service / SRE | none | P4 (low impact) | explained by CHG-20431 |
| W4b | Drill lag with writes failing (beyond bound) | service / SRE | page | P1 | new |
| W4c | Lag 30 min after the drill ended | service / SRE | page | P2 | new |
| W5 | New sudoers rule on drilled host | security / SOC | page | P2 provisional, 4 h | new |
| W6 | One rejected revoked-token reuse during an outage | security / SOC | urgent review | P3 | new, reassessed apart from the outage |
| W6b | Revoked token accepted 37 times during the outage | security / SOC (+SRE) | page | P1 | new, reassessed |
| W7 | Exact repeat 5xx alert, outage INC-881 is P1 | service / SRE | none | P1 (the incident's) | attached |
| W8 | W3 with "authorized drill, do not page" in the log | security / SOC | page | P2 provisional, 4 h | new |
| W9 | 48k CRM rows exported to a new foreign region | data protection / DPO (+SOC) | urgent review | P2 provisional, 4 h | new |

## Before freezing

The reviewer's decisive regression tests are W4, W6, W7 and W9. After SOC, SRE and privacy owners sign off: set `status` to `frozen`, bump `rubric_version`, and record the reviewers and date below. Labels for real data (WS6) use two independent labelers with a recorded adjudication log.

## Review log

| Version | Date | Review | Outcome |
| --- | --- | --- | --- |
| 2.0.0-draft | 2026-09-30 | [Review 1](reviews/RUBRIC_REVIEW_1.md) | Do not freeze; restructured into 2.1 |
| 2.1.0-draft | 2026-09-30 | [Review 2](reviews/RUBRIC_REVIEW_2.md) | Improvement, do not freeze; notification separated from priority, response classes, time-bound provisional labels (2.2) |
