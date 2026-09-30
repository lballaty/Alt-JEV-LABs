# Rubric review 1 (of 2.0.0-draft)

Received: 2026-09-30, via Libor Ballaty. Reviewer: external reviewer 1 (name not recorded in the repo).
The reviewer cited NIST incident response guidance, EDPB breach-notification guidance, Microsoft Sentinel alert grouping and Google SRE guidance on actionable paging. The received text did not include links, and those sources have not been re-checked here.

**Verdict: do not freeze 2.0.0.** The draft conflated event type, responsible team, urgency and paging, as if one determined the others.

## Findings and how 2.1.0-draft addresses them

| Rule | Reviewer's correction (summary) | 2.1.0-draft change |
| --- | --- | --- |
| R6 example | A lone failed SSH login does not establish an incident; an approved failover drill does not explain an invalid-user login. The correct label is security-related, retained for correlation, no page, low priority, and the window has no effect | Worked examples W1/W2 encode exactly this. The 2.0 example was wrong |
| R1 queues | Separate owner from disposition. "Audit log only" and "metrics only" are outcomes, not queues. Compliance review is a scheduled workflow | `event_types`, `owners` and `dispositions` are now separate fields. Compliance review is the owner `platform_compliance`, normally with the disposition `scheduled_ticket` |
| R2 precedence | No fixed ranking. Record one coordinating owner, chosen by the immediate response needed, plus secondary notifications | Precedence removed. The case author sets the primary type, the coordinating owner and secondary types/owners (W6) |
| R3 paging | Page when a named responder must take a time-sensitive action now, regardless of category. A lawful transfer abroad is not a breach, and the regulator-notification decision is separate | `page_now` only when urgency is immediate AND a responder can act. The type does not decide it. The data_protection definition says a lawful transfer is not a breach. W9 is a transfer with an unknown legal basis, sent to human review |
| R4 priority/times | Define P1–P4 by impact and required response. Targets are candidates needing local approval, and each must say what it measures | Priority = impact × urgency matrix. Response targets are marked "candidate, requires local approval" and mean *time to acknowledgement* |
| R5 score ranges | Delete fixed ranges per queue. Don't manufacture the answer key from a 0–100 number | Ranges deleted. The score primitive is now priority P1–P4 (ordinal). Any 0–100 model output is binned by the harness, as a measurement convention only |
| R6 maintenance | A window affects only specified expected signals on named assets and times. Unexpected behavior, scope violations or real compromise still escalate. Keep the original event and the suppression reason | `expected_activity` requires host, time AND signal to match `expected_signals`. `compromise_evidence` overrides it. Type and impact are kept, and the reason is recorded (W4, W5) |
| R7 open incident | Correlate only genuinely related repeats. A new failure mode, new asset, higher severity, or a security event during an outage means reassessment | Correlation requires the same entity, type and failure mode, and no increase in impact or urgency. Otherwise the event is reassessed and the reason recorded (W6, W7) |
| R8 criticality | Criticality informs impact for all cases, not a flat +10. A critical host doesn't make every failed login urgent | Bonus removed. `threatens_critical` on a critical asset requires impact ≥ moderate (checked), and a critical host alone changes nothing (W1) |
| R9 human review | Separate reasons: missing context, conflicting evidence, outside the taxonomy, reviewer disagreement. Never force a single label | `human_review_reasons` enum. Those cases get no page or priority target and are scored on deferral (W9) |

## Structural recommendations

| Recommendation | Status |
| --- | --- |
| Record observed/suspected/missing, type and owner, impact and urgency, context modifiers, disposition, priority or review reason for every case | `case_record_fields` in the rubric. `Evidence` and `Label` carry these fields |
| Rewrite worked examples first: lone failed SSH in and out of a window; burst then success; expected drill alert; unexpected security signal during the drill; security event during an open outage | `configs/domains/v2_worked_examples.json` W1–W9 (adds a spoof case and a data-protection case), each checked by `tests/test_rubric.py` |
| Two independent labelers, with disagreements and adjudications recorded; no silent conversion of uncertain cases to gold labels | Open. The adjudication log format is to be defined in WS6 before any labeling |
| Keep synthetic and real results separate; add an explicitly identified set of rare high-impact cases | PRACTICAL_EVAL_V2 updated (suite S10) |
| Report consequential errors (missed pages, improper suppression), per-class results and human-review rates, not just overall accuracy | PRACTICAL_EVAL_V2 reporting updated |
| Review the examples with SOC, SRE and privacy owners, and freeze only once they agree | Open. Freeze is blocked on this (tracker Q6) |
