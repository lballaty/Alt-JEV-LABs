# Rubric review 2 (of 2.1.0-draft)

Received: 2026-09-30, via Libor Ballaty (review pass 2 document). The reviewer cited NIST incident response guidance, EDPB breach guidance and Google SRE alerting guidance; no links were included, and they were not re-checked here.

**Verdict: substantial improvement, do not freeze yet.** Worked answers sometimes gave P4 because a page was suppressed, and sometimes gave P1 to a suspicious event without enough evidence of impact.

## Required changes and how 2.2.0-draft addresses them

| # | Reviewer's requirement | 2.2.0-draft change |
| --- | --- | --- |
| 1 | Keep incident priority separate from notification status. An attached repeat must not become P4 (W7), and an explained alert must not be treated as having no impact (W4) | Priority is computed once from the observed facts. Change explanation and incident attachment set `notification: none` only. An attached repeat takes the **incident's** priority (W7 → P1). The explained drill lag is P4 because its assessed impact is low, and the same event with a higher impact is P2 (test `W4_explanation_suppresses_notification_not_priority`) |
| 2 | Make human review time-bound: a named triage owner and deadline, with urgent escalation when the known facts indicate possible ongoing harm | "Human review, no target" is replaced by **provisional** labels. Each has a reason, the missing facts, a triage owner (the coordinating owner) and a deadline (P1 1 h, P2 4 h, P3 end of business day, P4 2 business days). The normal notification rule still applies, so possible ongoing harm pages or escalates (W3, W5, W9) |
| 3 | Resolve the contradictions between the priority table, the paging rule and the targets | Response classes are defined first: P1 = immediate + high impact (15 min), P2 = immediate + low/moderate (1 h), P3 = same day, P4 = scheduled or retained. Every paged event is P1 or P2 (tested). High + same day is now P3 (same-day target). Impact "none" with any urgency is rejected as invalid |
| 4 | Treat claims inside logs as untrusted, but not all log content as irrelevant; list the other trusted context | `untrusted_claims` rule: authorization or instruction text has no authority, but the observed action, actor, time and outcome are evidence (events now carry `actor`/`outcome`). Trusted context is the change calendar and approved test scope, the incident register, asset records and identity records |

## Worked examples

| Case | Review | 2.2 answer |
| --- | --- | --- |
| W1–W2 | Agree; clarify that "SOC · keep" is not a ticket per failure | No notification, P4. The SOC owns correlation; no ticket per event |
| W3 | Page defensible; P1 needs more context | Provisional, page SOC, P2, triage within 4 h. Missing: login validity, expected source, access obtained |
| W4 | No page only within the drill's bounds and duration; don't equate no page with P4 | Expected signals carry `max_impact`. W4 (within bound) is explained, no notification, P4 from low impact. **W4b** (writes failing, beyond bound) pages SRE at P1. **W4c** (after the window) pages SRE at P2 |
| W5 | Page reasonable; P1 not established | Provisional, page SOC, P2, 4 h. Missing: actor authorization, what the rule grants, whether it is in use |
| W6 | A single rejected reuse is not automatically P1; assess it separately from the outage | Rejected, one attempt: urgent review, P3, no page, reassessed separately from INC-881. **W6b** (accepted, 37 attempts) pages SOC at P1 |
| W7 | Attach without a second notification; keep the outage's priority | Attached, no notification, **P1** (the incident's priority) |
| W8 | Same provisional disposition as W3 | Identical to W3 (spoof text ignored; observations used) |
| W9 | Deadline for Privacy/DPO, route to SOC if exfiltration suspected; a foreign region alone is not a breach | Provisional, urgent review, P2, Privacy/DPO triage within 4 h, SOC as secondary owner. Missing facts cover destination approval, transfer mechanism, job legitimacy and whether it continues |

## Questions

| # | Reviewer's answer | Status |
| --- | --- | --- |
| A1–A2 | Adequate as a starting scope, provided "none"/"keep" are outcomes, not teams | The "none" owner is removed; retained is a handling outcome. Routine and telemetry have no receiving team |
| A3–A4 | Change until priority and targets are consistent | Addressed by change 3 |
| A5 | Agree; uncertain, potentially serious events need an urgent triage path | Addressed by change 2 |
| A6 | Agree; each human-review outcome needs a reason and deadline | Addressed by change 2 |

The reviewer's proposed six-step decision order is adopted, lightly edited, as `decision_order` in the rubric.
