# Agent ownership and coordination

Status: **current as of 2026-10-04, from `main`.** Purpose: tell every agent which files and workstreams are whose, and how work is handed over. The live status of each workstream is in `docs/TRACKER.md`; this file does not duplicate it. If the two disagree, the tracker wins and this file must be fixed in the same PR.

## Who owns what

| Owner | Scope | Status |
| --- | --- | --- |
| **Calibration agent** ("other agent") | Finite JSON decoding, validation calibration, v2 blueprint (`docs/BLUEPRINT_V2.md`, `training/calibrate.py`, and the v1 files it changed) | Merged (PR #1). Edits to its files by other agents go through a PR. |
| **Planning session** | `docs/DATASET_PLAN_V2.md`, `docs/PRACTICAL_EVAL_V2.md`, `docs/TRACKER.md`, rubric (WS2, frozen 2.4.0), manager docs, realism research (WS10) | Merged except WS10 (in progress) |
| **Seed-registry session** (cloud session `session_016suEmxQMsUKD66MEcF2kow`) | WS1: `data/seed_registry.py`, `data/entity_filler.py`, `data/seeds/*`, `tests/test_seed_registry.py`; this file | Merged (PR #3). |
| **Unassigned** | WS3 cohort generator, WS4 runner/reporter, WS5, WS6, WS7, WS8 | See tracker. Take one by writing your name in the tracker's Owner column in the same PR that starts it. |
| **codex-ebook-companion-01** (this ebook/companion session) | The Deterministic Edge publishing workspace in `lballaty/searchingfool-publishing` and companion-repository coordination; no Alt-JEV-LABs implementation workstream claimed | Acknowledged rules; coordination edits to shared docs via PR |
| **Project owner** (Libor Ballaty) | Every decision in the tracker's decisions log and open questions; final say on scope | — |

## Working rules

1. **Everything an agent does must be visible on GitHub `main`.** Agents do not share a session or filesystem; the repository is the only channel. A file on an unmerged branch does not exist for the other agent.
2. **Standing instruction from the project owner (2026-10-04, D21): merge to `main` automatically and update the trackers in the same change; do not wait for a reviewer.** This overrides `AGENTS.md` rule 6 ("seek review before merging to main") for ordinary work. Open a PR (so there is a record), make sure tests pass, merge it, and update `docs/TRACKER.md` in that same PR. The owner can revoke this at any time.
3. **Guardrails that still apply:** do not merge with failing tests; never commit weights, secrets or identifiable traces; never edit a frozen artifact (rubric 2.4.0) without a recorded decision; do not enable agent or enforcement actions from classifier output (`AGENTS.md` rule 5); do not fabricate results.
4. **Decisions are the owner's.** An agent may propose in the tracker's open questions but may not record a decision as made unless the owner stated it. Record it as the next `D<n>` row with its date and source.
5. **Start from current `main`.** Fetch before writing; stale checkouts caused wrong conclusions on 2026-10-04.
6. **Edit a file another owner holds only through a PR** that says so, and update the tracker.

## Acknowledgement

Agents record acknowledgement by appending a row in the tracker's decisions log on `main`, or by a comment on the PR that introduced a change to this file.

| Agent | Acknowledged | Date |
| --- | --- | --- |
| Seed-registry session (WS1) | Authored; follows these rules | 2026-10-04 |
| Calibration agent | _not yet recorded_ | |
| Planning session | _not yet recorded_ | |
| codex-ebook-companion-01 | Read `AGENTS.md`, this file, and `docs/TRACKER.md`; follows D21 auto-merge, ownership, and safety rules | 2026-10-04 |
