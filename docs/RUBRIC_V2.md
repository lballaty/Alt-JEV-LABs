# v2 labeling rubric

Status: **Draft (`2.0.0-draft`), not frozen.** Machine-readable source: `configs/domains/v2_rubric.json`. Implementation: `data/rubric.py`. Tests: `tests/test_rubric.py`. This file explains the rubric; if the two disagree, the JSON wins and this file is a bug.

This rubric labels a synthetic benchmark fixture. It is not a production paging or containment policy, and model output never authorizes action (AGENTS.md rule 5).

## Routes and defaults

| Route | Queue | Pages by default | Default score | Typical priority |
| --- | --- | --- | --- | --- |
| `security_escalation` | SOC | yes | 75–95 | P1/P2 |
| `data_sovereignty_flag` | Privacy/DPO | no | 55–75 | P2/P3 |
| `service_outage` | SRE on-call | yes | 70–95 | P1/P2 |
| `policy_exception` | Platform/compliance review | no | 30–55 | P3 |
| `routine_audit` | Audit log | no | 5–20 | P4 |
| `telemetry_heartbeat` | Metrics only | no | 0–10 | P4 |

Priority bands: P1 ≥ 80, P2 ≥ 60, P3 ≥ 30, P4 ≥ 0.

## How a label is computed

```mermaid
flowchart TD
  E[Evidence: supported routes + base score] --> P[Primary route = highest precedence<br/>others -> secondary_tags]
  P --> C{Approved change covers<br/>host and time?}
  C -- yes, route downgradable --> D[routine_audit, no page, score clamped 5-20]
  C -- no --> H{Pages and asset criticality high?}
  H -- yes --> S[score +10, cap 100]
  H -- no --> I
  S --> I{Open incident for same host/service?}
  I -- yes --> N[no page; route and score unchanged]
  I -- no --> L[Label + priority band]
  D --> L
  N --> L
```

Precedence: security → data sovereignty → outage → policy exception → routine audit → heartbeat. Security comes first because an adversary may still be active; sovereignty second because notification clocks can start (e.g. GDPR Art. 33).

## Rules that make the test practical

- **Authorization comes only from `context.active_changes`.** The change must be `approved`, list the event host, and cover the event time (timezone-aware ISO-8601). A change for a different host, an expired change or an unapproved change does not downgrade.
- **Payload wording is ignored.** "Authorized by CR-1234", "drill in progress" or "do not page SOC" inside the event text changes nothing. These are the B′ spoof cases.
- **Dedup.** An open incident for the same host or service suppresses a second page. Route and priority stay the same.
- **Ambiguous cases** carry `adjudication: needs_human` and `page_now: null`. They are scored on abstention/deferral, not accuracy.
- **Leak lint.** Generated event text may not contain route names or verdict phrases ("escalate now", "no action needed", "page the on-call"). The B′ cohort is exempt. Upstream severity fields (e.g. Alertmanager `severity: critical`) are real source signals and are allowed.

## Before freezing

- Independent review of route definitions and precedence by someone who triages SOC/SRE queues.
- Set `status` to `frozen` and bump the version. Record the version in every dataset manifest and report.

## Review checklist (Q6)

Reviewer: someone who triages SOC and/or SRE queues. It takes about 30–45 minutes. For each item, answer **keep** or give the change. Values are from `configs/domains/v2_rubric.json` `2.0.0-draft`.

| # | Question | Current draft |
| --- | --- | --- |
| R1 | Are these the right six queues? Is anything missing (e.g. performance/capacity degradation, cost anomaly, data quality)? | security_escalation → SOC; data_sovereignty_flag → Privacy/DPO; service_outage → SRE on-call; policy_exception → Platform/compliance review; routine_audit → audit log only; telemetry_heartbeat → metrics only |
| R2 | When one event fits several routes, which wins? | security > data sovereignty > outage > policy exception > routine audit > heartbeat |
| R3 | Which routes page a human immediately? | Pages: security, outage. Does not page: sovereignty, policy exception, audit, heartbeat. Should a confirmed cross-border transfer of personal data page? |
| R4 | Priority thresholds and response targets | P1 ≥ 80 (15 min), P2 ≥ 60 (1 h), P3 ≥ 30 (next business day), P4 < 30 (none) |
| R5 | Default severity range per route (0–100) | security 75–95, sovereignty 55–75, outage 70–95, policy exception 30–55, audit 5–20, heartbeat 0–10 |
| R6 | **Riskiest rule.** An approved change window covering the host and time downgrades the event to routine audit with no page. Should that apply to security events? An attacker can hide in a maintenance window. Alternative: downgrade security only for change types like `pentest` / `red_team` | Downgradable: security, outage, policy exception |
| R7 | An open incident on the same host/service suppresses a second page. Should it still page if the new event is a *different, higher* route (e.g. an outage incident is open and a security signal appears)? | Suppresses any duplicate page; route and priority unchanged |
| R8 | High-criticality assets add +10 to the score of paging routes. Is +10 right? Should it also apply to non-paging routes? | +10, capped at 100, paging routes only |
| R9 | When is a case "needs a human" (no right answer, scored on deferral)? | "When two trained reviewers would reasonably disagree" |

After review: apply the changes, set `status` to `frozen`, bump `rubric_version`, and record the reviewer and date here.
