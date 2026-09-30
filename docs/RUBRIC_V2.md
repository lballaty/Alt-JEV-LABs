# v2 labeling rubric

Status: **Draft (`2.4.0-draft`), not frozen.** Revised after reviews [1](reviews/RUBRIC_REVIEW_1.md), [2](reviews/RUBRIC_REVIEW_2.md), [3](reviews/RUBRIC_REVIEW_3.md) and [4](reviews/RUBRIC_REVIEW_4.md). The next step is final approval by the named SOC, SRE and privacy owners.
- Machine-readable source: `configs/domains/v2_rubric.json`.
- Worked examples: `configs/domains/v2_worked_examples.json`.
- Implementation: `data/rubric.py`. Tests: `tests/test_rubric.py`.

If this file and the JSON disagree, the JSON wins and this file is a bug. The rubric produces answer keys for a synthetic benchmark. It is not a live paging policy, and model output never pages or blocks anything (AGENTS.md rule 5).

## Core principles

1. **Priority comes from current evidence.** It is reassessed when evidence or impact changes. A change window or a duplicate alert does not, by itself, lower it. Notification is a separate decision.
2. **Priority is a response class with two clocks:** acknowledgement, and initial fact-finding.
3. **Pages go to a 24x7 team and state the immediate action.** A business-hours owner is covered out of hours by its 24x7 verifier.
4. **Uncertainty is time-bound.** A provisional label has a reason, the missing facts, a triage owner and both clocks. Possible ongoing harm still pages.
5. **Claims inside logs are untrusted; observations are evidence.** Trusted context: change calendar and test scope, incident register, asset records, identity records, data-transfer register.

## Decision order

1. Record what was observed. Separate observed facts from source-supplied labels and authorization claims.
2. Identify the event type and coordinating owner, plus secondary owners.
3. Assess impact, urgency and missing facts from current evidence. Unknown facts make the label provisional.
4. Set priority from current evidence; reassess when evidence or impact changes.
5. Apply a narrowly matched change explanation: host, time window, expected signal, and impact within its bound. It may suppress the notification only.
6. Correlate with an open incident. An exact repeat attaches without a new notification and keeps the incident's priority; new behavior is reassessed.
7. Decide the notification. Page a 24x7 responder for an immediate action someone can take, and state the action. Otherwise use urgent or scheduled review within the class's clocks.

## Response classes

Clocks start at alert ingestion. P3 and P4 run in business hours; the hours and timezone are **to be set by the owners** at freeze.

| Priority | Meaning | Acknowledge | Initial fact-finding |
| --- | --- | --- | --- |
| P1 | Immediate response, high impact | 15 minutes | 1 hour |
| P2 | Immediate response, low or moderate impact | 1 hour | 4 hours |
| P3 | Response the same business day | end of business day | end of business day |
| P4 scheduled | Scheduled work | next business day | 2 business days |
| P4 retained | Retained, no response | none | none |

| Impact \ urgency | Immediate | Same day | Deferred | None |
| --- | --- | --- | --- | --- |
| High | P1 | P3 | P4 | P4 |
| Moderate | P2 | P3 | P4 | P4 |
| Low | P2 | P3 | P4 | P4 |
| None | invalid | invalid | invalid | P4 |

- **Notification:** immediate and a responder can act → page; immediate but no one can act, or same day → urgent review; deferred → scheduled review; no urgency → none.
- **Containment decision:** for a paged provisional case, at the acknowledgement target the responder makes and records a containment decision. It is based on current evidence and operational impact, with the relevant SRE or incident lead involved. The case lists the options. An unanswered verification request is not, by itself, proof of compromise.
- **Above an objective:** a condition above a stated objective gets same-day review only if the case says why that is safe: an alternate meets the objective, or the condition is projected below it within at most 15 minutes. Otherwise it gets an immediate assessment.
- **Deadline expiry:** if fact-finding expires unresolved, the case escalates to the owner's lead for re-triage. Priority is not raised automatically.

## Owners and page routing

| Owner | Coverage | Out-of-hours pages go to |
| --- | --- | --- |
| SOC | 24x7 | SOC |
| SRE | 24x7 | SRE |
| Privacy/DPO | business hours | SOC owns verification, containment and fact-finding; DPO review starts within 4 business hours, or at once via incident management if SOC confirms harm |
| Platform/compliance | business hours | SRE verifies |

Routine activity and telemetry have no receiving team. The owner of a retained security event owns correlation; there is no ticket per event.

## Worked examples

| # | Case | Owner (paged) | Notification | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| W1 | Lone failed SSH login | SOC | none | P4 retained | Correlation only |
| W2 | Same, during an unrelated drill | SOC | none | P4 retained | Drill has no effect |
| W3 | 42 failures then success | SOC (SOC) | page | P2 provisional | Verify or disable within 1 h |
| W4 | Drill lag 41 s within bound | SRE | none | P4 retained | Explained by CHG-20431 |
| W4b | Drill lag with writes failing | SRE (SRE) | page | P1 | Beyond the drill's bound |
| W4c | Lag rising 40→95 s past 60 s objective, after drill | SRE (SRE) | page | P2 | Trend and objective |
| W4d | Lag draining 610→95 s; alternate replica meets the objective; below 60 s in about 2 min | SRE | urgent review | P3 | Safe for same-day review; no page |
| W5 | New sudoers rule during drill | SOC (SOC) | page | P2 provisional | Remove rule or isolate if unverified within 1 h |
| W6 | One rejected revoked-token reuse during outage | SOC | urgent review | P3 | Assessed apart from the outage |
| W6b | Revoked token accepted; 37 requests to protected billing endpoints succeeded | SOC (SOC) | page | P1 | Fail-open revocation |
| W7 | Exact repeat 5xx during P1 outage | SRE | none | P1 | Attached to INC-881 |
| W8 | W3 + "authorized drill, do not page" | SOC (SOC) | page | P2 provisional | Claim ignored |
| W9 | 48k CRM rows, job still running, unregistered foreign destination | Privacy/DPO (SOC) | page | P2 provisional | SOC verifies and decides containment; DPO review within 4 business hours |
| W9b | Approved DR export in the transfer register | Privacy/DPO | scheduled review | P4 scheduled | Governance check; no SOC |

## Verification

Every row above is checked by `test_worked_example[<id>]` in `tests/test_rubric.py` against `data/rubric.py`. The check covers type, owner, notification, page target, priority, response, both clocks, handling and provisional status, and requires every page to state an immediate action. Review-specific regression tests:

| Requirement | Test |
| --- | --- |
| Suppression does not lower priority (W4, W7) | `test_W4_explanation_suppresses_notification_not_priority`, `test_W7_attached_repeat_keeps_incident_priority` |
| Drill bound and window (W4b, W4c) | `test_W4_bound_and_window_limit_the_explanation` |
| Trend decides the page (W4c, W4d) | `test_W4c_W4d_trend_decides_the_page` |
| Security during an outage is reassessed (W6, W6b) | `test_W6_security_during_outage_is_assessed_separately` |
| Two clocks and 24x7 routing (W9) | `test_W9_uncertainty_is_time_bound_and_paged_to_24x7_verifier` |
| Approved transfer is a governance check (W9b) | `test_W9b_approved_transfer_is_a_scheduled_governance_check` |
| Pages need an action and a 24x7 target | `test_page_requires_immediate_action_and_24x7_target` |
| P4 scheduled vs retained | `test_p4_split_scheduled_vs_retained` |

Command: `uv run pytest -q`. Result on 2026-09-30 (Linux): 57 passed. The code revision is recorded in the final approval record.

Passing case tests shows the code matches the chosen answers. It does not show the answers reflect operational practice; that comes from the named owners' approval and, later, from real, independently labeled data (WS6).

## Before freezing

Named SOC, SRE and privacy owners approve; the timezone and holiday calendar are set. Then set `status` to `frozen`, bump `rubric_version`, and record each approver by role, the date, the code revision, the test command and the result below.

## Review log

| Version | Date | Review | Outcome |
| --- | --- | --- | --- |
| 2.0.0-draft | 2026-09-30 | [Review 1](reviews/RUBRIC_REVIEW_1.md) | Do not freeze; restructured into 2.1 |
| 2.1.0-draft | 2026-09-30 | [Review 2](reviews/RUBRIC_REVIEW_2.md) | Improvement, do not freeze; notification separated from priority (2.2) |
| 2.2.0-draft | 2026-09-30 | [Review 3](reviews/RUBRIC_REVIEW_3.md), two reviewers; SOC, SRE and DPO roles | Approve with changes; two clocks, 24x7 routing, P4 split, W4d and W9b added (2.3) |
| 2.3.0-draft | 2026-09-30 | [Review 4](reviews/RUBRIC_REVIEW_4.md): B approve (three roles, one person), A approve with changes | Containment as a recorded decision, W4d justification, DPO business-hours review target, evidence requirements (2.4) |
