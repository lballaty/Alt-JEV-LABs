# Agent ownership and coordination

Status: **current as of 2026-10-04, from `main`.** Purpose: tell every agent which files and workstreams are whose, and how work is handed over. The live status of each workstream is in `docs/TRACKER.md`; this file does not duplicate it. If the two disagree, the tracker wins and this file must be fixed in the same PR.

## Who owns what

**There are exactly two agents: `claude-cloud-ws1-01` and `codex-ebook-companion-01`.** There is no calibration agent and no planning agent. Those names in older docs and in the tracker's history ("other agent", "this session", "calibration agent", "planning session") are earlier sessions whose work is merged and which have ended. They will not act, review or acknowledge anything. Nothing is waiting on them. Unclaimed work is unassigned, not held by them.

| Owner | Scope | Status |
| --- | --- | --- |
| **`claude-cloud-ws1-01`** | All implementation work: WS1 (merged), WS2 rubric (merged, frozen 2.4.0), WS3, WS7, and any unassigned WS (WS4, WS8, ...) it picks up. Owns every code file, including `evaluation/*`, `models/*`, `training/*` and `docs/BLUEPRINT_V2.md` (earlier sessions that wrote them have ended) | Active |
| **codex-ebook-companion-01** (this ebook/companion session) | The Deterministic Edge publishing workspace and companion coordination; planning docs (`docs/DATASET_PLAN_V2.md`, `docs/PRACTICAL_EVAL_V2.md`, `docs/TRACKER.md`), manager docs/WS9 handoff coordination, WS10 realism research. No implementation/code workstream claimed; `docs/BLUEPRINT_V2.md` and frozen rubric stay with Claude | Acknowledged rules; coordination edits to shared docs via PR |
| **Project owner** (Libor Ballaty) | Every decision in the tracker's decisions log and open questions; final say on scope | — |

Related repositories: the ebook text and its example code live in two private repositories (D34); their addresses are not recorded here, and each maps back to this repository. Book-facing coordination is `codex-ebook-companion-01`'s; implementation ownership of the example code is not yet assigned.

## Agent IDs

Use your ID in tracker Owner cells, commit trailers, PR bodies and the acknowledgement table, so any agent can tell who did what from GitHub alone.

| Agent ID | Who | Scope |
| --- | --- | --- |
| `claude-cloud-ws1-01` | Claude Code cloud session `session_016suEmxQMsUKD66MEcF2kow` (peer name `alt-jev-labs-e7`) and the subagents it launches (WS3, WS7 branches `feat/ws3-cohort-generator`, `feat/ws7-chat-module`) | WS1 (merged), WS3, WS7; this file and D21/D23 |
| `codex-ebook-companion-01` | Ebook/companion session | Ebook/companion coordination (D22); planning docs, WS9 handoff coordination and WS10 research (D25); excludes calibration/code/WS4 and Claude's blueprint/rubric |

## Non-conflicting planning handover — D25

Libor requested takeover of prior calibration/planning work only where it does not conflict. The latest ownership assigns all implementation files to Claude, so calibration code and WS4 remain with Claude. `codex-ebook-companion-01` takes planning/documentation maintenance, WS9 handoff coordination and WS10 research. This does not grant write ownership of the external manager's implementation. Preserve open PR #17 and existing realism/manager branches or bundles; inventory and reconcile them before overlapping edits. Shared tracker and ownership changes continue through PRs from current main.

## Working rules

1. **Everything an agent does must be visible on GitHub `main`.** Agents do not share a session or filesystem; the repository is the only channel. A file on an unmerged branch does not exist for the other agent.
2. **Standing instruction from the project owner (2026-10-04, D21): merge to `main` automatically and update the trackers in the same change; do not wait for a reviewer.** This overrides `AGENTS.md` rule 6 ("seek review before merging to main") for ordinary work. Open a PR (so there is a record), make sure tests pass, merge it, and update `docs/TRACKER.md` in that same PR. The owner can revoke this at any time.
3. **Guardrails that still apply:** do not merge with failing tests; never commit weights, secrets or identifiable traces; never edit a frozen artifact (rubric 2.4.0) without a recorded decision; do not enable agent or enforcement actions from classifier output (`AGENTS.md` rule 5); do not fabricate results.
4. **Decisions are the owner's.** An agent may propose in the tracker's open questions but may not record a decision as made unless the owner stated it. Record it as the next `D<n>` row with its date and source.
5. **Start from current `main`.** Fetch before writing; stale checkouts caused wrong conclusions on 2026-10-04.
6. **Edit a file another owner holds only through a PR** that says so, and update the tracker.
7. **Private information stays out of this public repository (D35).** Nothing about the private repositories goes into this public repository: no repository names, URLs, file paths, commit hashes, unpublished titles or summaries of their content. This applies to files, commit messages, PR titles and descriptions, and comments. Refer to them only as "the ebook workspace" and "the example repository", at a high level. Mapping detail lives in the private repositories (their LAB-MAPPING files). Earlier leaks stay in history (owner chose not to rewrite it). Before every commit and PR, check the text for private names, paths and content.

## Acknowledgement

Agents record acknowledgement by appending a row in the tracker's decisions log on `main`, or by a comment on the PR that introduced a change to this file.

| Agent | Acknowledged | Date |
| --- | --- | --- |
| Seed-registry session (WS1) | Authored; follows these rules | 2026-10-04 |
| `claude-cloud-ws1-01` | Chose this ID; read `AGENTS.md`, this file and the tracker; follows D21 | 2026-10-04 |
| codex-ebook-companion-01 | Read `AGENTS.md`, this file, and `docs/TRACKER.md`; follows D21 auto-merge, ownership, and safety rules | 2026-10-04 |
