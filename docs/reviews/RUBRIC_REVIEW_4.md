# Rubric review 4 (of 2.3.0-draft, confirmation pass)

Received 2026-09-30 via Libor Ballaty, from two reviewers working from the pass 4 PDF.

## Reviewer B: approve (all three roles)

SOC, SRE and Privacy/DPO roles all **Approve**, with no changes. Settings proposed: business hours 08:00–18:00 Mon–Fri; timezone Europe/Prague **or** Europe/Lisbon; statutory holiday calendar of the operating entity.

All three role sign-offs carry the same name (Libor Ballaty). Reviewer A points out that each role must be signed by someone authorized to represent it. Until named domain owners sign, this is recorded as **roles signed by one reviewer, not independent owners**.

## Reviewer A: approve with changes

Agreed: F1, F4, F5 (P4 split), F6 (W4c), F7. W6b is a credible P1. Four targeted corrections, and no redesign needed:

| Issue | 2.4.0-draft change |
| --- | --- |
| W4d is still above the 60 s objective; state why same-day review is safe | W4d now states the alternate replica db-8 meets the objective (3 s) and db-7 drains about 17 s/min, projected below 60 s within about 2 minutes. New authoring rule: an above-objective condition gets same-day review only with such a justification (alternate meets objective, or projected below it within at most 15 min); otherwise immediate assessment |
| One-hour fallbacks are too automatic; an unanswered verification is not proof of compromise | Containment is now a **recorded decision** at the acknowledgement target, based on current evidence and operational impact, with the relevant SRE, platform or incident lead involved. Options are listed (W3/W8: terminate session, disable account, monitor with tightened access; W5: roll back rule, restrict account, isolate host; W9: pause job, revoke credentials, complete under watch). W6b's fail-closed change is coordinated with the INC-881 incident lead |
| W9 promised a 4 h DPO assessment the DPO's staffing can't provide | Out of hours the 24x7 verifier (SOC) owns verification, containment and the fact-finding clock (`triage_owner = soc`). The DPO review starts within **4 business hours**, or at once via incident management if SOC confirms an unapproved export. No out-of-hours DPO assessment is promised |
| Sign-off and verification not evidenced: blank settings, no code revision or test command, one person in three roles | Business hours filled from reviewer B's proposal. Timezone and holiday calendar still need one answer. The final approval record will include the code revision, the command (`uv run pytest -q`), the result, and the named approver per role |

Reviewer A's closing point is recorded as a validity limit: passing case tests shows the code matches the chosen answers; it does not show the answers reflect operational practice. That comes from the named owners' approval, and later from real, independently labeled data (WS6).

## Outcome

2026-09-30: all four of reviewer A's changes applied in 2.4.0-draft. Test coverage of `data/rubric.py` was brought to 100% of lines and branches. The project owner then closed the review, and the rubric was **frozen as 2.4.0**. Reviewer A then checked 2.4 and had no comments, so both reviewers approve. The single-person role sign-off remains recorded as a validity limit in `docs/RUBRIC_V2.md`.
