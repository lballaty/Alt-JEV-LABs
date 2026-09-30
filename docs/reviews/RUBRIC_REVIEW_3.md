# Rubric review 3 (of 2.2.0-draft, sign-off pass)

Received: 2026-09-30, via Libor Ballaty, from two reviewers working from the pass 3 sign-off PDF. Reviewer B answered in the SOC, SRE and Privacy/DPO roles. Both reviewers' verdict: **approve with changes**, not yet frozen. Reviewer A noted that the Claude link was not readable outside the account; reviewers should get the PDF.

## Findings and how 2.3.0-draft addresses them

| Topic | Reviewer A | Reviewer B | 2.3.0-draft change |
| --- | --- | --- | --- |
| Two clocks | P2's 1 h acknowledgement vs "triage 4 h" reads as permission to wait; say what to do immediately | What happens if the 4 h deadline expires? SOC: containment guidance if facts are not resolved within 1 h | Each class has an **acknowledgement** target and an **initial fact-finding** deadline (P2: 1 h / 4 h). Every page states the **immediate action**, including the containment decision if the key fact is unverified at the acknowledgement target. When fact-finding expires unresolved, the case escalates to the owner's lead for re-triage; priority is not raised automatically |
| Paging and ownership | W9 contradicts "possible ongoing harm pages"; "SOC told" needs a trigger | Does P2 always page? DPO has no 24/7 pager; SOC should hold it and bring DPO in on an expedited path | P1/P2 means immediate response; it pages only when a responder can act. Owners have **coverage**: SOC and SRE are 24x7, Privacy/DPO and platform/compliance are business hours. A page always goes to a 24x7 team, and a business-hours owner's page goes to its **verifier** (DPO → SOC, platform/compliance → SRE) |
| "Set once" | Priority can change with new evidence | — | Wording: priority is set from current evidence and reassessed when evidence or impact changes; a change window or duplicate alert does not, by itself, lower it |
| P4 targets | Inconsistent; specify clock start, business hours, timezone | — | P4 splits into **scheduled** (acknowledge next business day, fact-finding 2 business days) and **retained** (no target). Clocks start at alert ingestion. Business hours and timezone are placeholders for the owners to set at freeze |
| W4c | 95 s after the drill is underdetermined; add threshold, trend, objective | Draining lag → P3; static or rising → P2 page | W4c now states lag rising 40 → 95 s past a 60 s recovery objective → P2 page. **New W4d**: lag falling 610 → 95 s, writes healthy → P3 same-day review |
| W6b | Say what "accepted" means and what was reached | Agree (failing open or revocation failed) | Raw log and facts now state: the auth layer skipped revocation (cache fallback) and accepted the token; 37 requests to protected billing endpoints returned 200 |
| W9 | Explicit page rule; SOC trigger; foreign region ≠ breach | SOC gets the 24/7 page to verify; DPO within 4 h to protect the GDPR Art. 33 72-hour clock | W9 states the job is still running and the destination is unregistered. That is possible ongoing harm, so it **pages SOC** to verify, with pause/revoke if unverified within 1 h, and DPO assesses within 4 h or immediately if SOC confirms an unapproved export. **New W9b**: an approved export listed in the transfer register is a scheduled DPO governance check with no SOC involvement |
| Evidence of implementation | The PDF can't show the rules and tests implement the answers | Formalize changes as test criteria | Every case is checked by `tests/test_rubric.py` against `data/rubric.py`. New dedicated tests cover the two clocks, 24x7 routing, P4 split, W4c/W4d and W9/W9b. The next sign-off document carries a verification section |

## Agreed as written (both reviewers)

W1, W2, W4, W6, W7, W8. W3 and W5 as provisional P2 pages, now with separate clocks and containment actions. W4b as P1: reviewer B (SRE role) confirmed high operational impact, as reviewer A requested.

## Still required before freeze

- Owners confirm the changed cases (W4c, W4d, W6b, W9, W9b) and the new clock/routing rules.
- Owners set business hours and timezone.
- The automated tests pass on the rubric version being frozen, which is recorded in the review log.
