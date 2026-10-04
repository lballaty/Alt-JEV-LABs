# Handoff: llamaCPPManager benchmark-support work

Status: **Delivery bundle verified in `arionrepo/llamaCPPManager`; application and Mac validation remain pending.** The previous authoring session reported Linux implementation/tests. This session verified the archived delivery, not the runtime behavior. This document contains **no manager code**. It is the checklist that makes sure everything lands in the manager repo.

## Where the work is

| Item | Value |
| --- | --- |
| Delivery file | [`llamacppmanager-benchmark-support.tgz`](https://github.com/arionrepo/llamaCPPManager/blob/def9917e324b491a94ad4d4e8b843bca2d160480/llamacppmanager-benchmark-support.tgz) (verified in manager main on 2026-10-04). Contains `feat-benchmark-support.bundle`, `patches/0001–0003`, `APPLY.md` |
| tgz sha256 | `7e083c6821f454a9648f6a2c44f7f1d1e5f0e88e4c974118a8619833e870733b` |
| Base commit | `b7d27f9a71fd7663147168f408a8190d8de1bdea` (VERSION 2026.09.10.2) |
| Branch | `feat/benchmark-support` |
| Commit 1 | `22c419727015b92930bc03e9c3c472983f8f81f5`: docs+deps: benchmark support tracker; pin mcp<2 (M0) |
| Commit 2 | `19dde33f172e9b4e4211496c84a75d4e5ad81eef`: feat: opt-in benchmark support |
| Commit 3 | `16484405e3f9e9dc0487867c9c6d8c0ac1b87326`: docs: GUI impact, auto-restart rationale, MLX verification plan |
| Size | 17 files, +1592 / −4 lines vs base |
| Linux result | 181 passed / 6 failed / 3 skipped. Reported by the previous authoring session: the 6 are the same macOS-only failures as the baseline (160 passed / 6 failed) |

After fetching the original bundle, verify its three-commit chain against the listed hashes. If later Mac fixes are added, the original tip must remain an ancestor and new commits must be listed separately; do not require the branch to contain only three commits forever. Applying patches with `git am` can change commit hashes because committer metadata changes, so prefer the bundle when preserving original identity.

## Delivery audit — 2026-10-04

Owner: `codex-ebook-companion-01` (WS9 coordination).

| Check | Observed result |
| --- | --- |
| Manager main inspected | `def9917e324b491a94ad4d4e8b843bca2d160480`; VERSION remains 2026.09.10.2 |
| Bundle file blob | `3d64d37a03682d5be15a7adc3997988d9d3ea3cd` |
| Archive SHA-256 computed locally | Matches `7e083c6821f454a9648f6a2c44f7f1d1e5f0e88e4c974118a8619833e870733b` |
| Archive members | APPLY.md, one Git bundle, and patches 0001–0003 present |
| Bundle advertised ref | `refs/heads/feat/benchmark-support` → `16484405e3f9e9dc0487867c9c6d8c0ac1b87326` |
| Bundle prerequisite header | `b7d27f9a71fd7663147168f408a8190d8de1bdea` |
| Patch From headers | Match the three recorded commit IDs |
| Applied branch evidence | Listed manager branches: main and feature/colima-updates-and-notifications; no benchmark-support branch |
| Applied tracker evidence | Manager main tree does not contain docs/BENCHMARK-SUPPORT-TRACKER.md |
| Runtime/Mac/GUI checks | Not run by this session; Linux suite results below are inherited reports |

Archive checksum plus metadata checks establish delivery integrity against the recorded artifact. They do not establish patch applicability, full Git object connectivity, installed CLI behavior or Mac release readiness. The bundle's prerequisite must exist before `git bundle verify` and fetch on the Mac.

The historical claim that the work is absent from the manager repository is corrected: **the archive is present; the implementation is not shown applied.** No manager code was edited and no live process was touched.

## What is still to do in the manager repo

| # | Work | Where it is specified |
| --- | --- | --- |
| H1 | Delivery integrity verified; apply the bundle on Mac and verify prerequisite, full object connectivity and original commit ancestry | `APPLY.md` in the tgz; delivery audit above |
| H2 | Run the macOS baseline on unchanged `main` first, then the suite on the branch: no new failures | manager `docs/BENCHMARK-SUPPORT-TRACKER.md` |
| H3 | **GUI U1** (required before locks are used): show CLI stderr in an alert when start/stop/restart/start-all exit non-zero; "Test lock active" banner from `locks --json`. Build + test per `docs/SWIFT-AGENT-STANDARD.md` | manager tracker, "GUI impact" |
| H4 | **MLX verification checklist**, using the pipx-installed CLI | manager tracker, "MLX verification" |
| H5 | Mac verification checklist (manifest, memory footprint vs RSS, system values, lock behavior, offline) | manager tracker |
| H6 | Decide: keep the lock's restart suppression, or replace it with "untrack before run" | manager tracker, "Auto-restart vs. test lock" |
| H7 | Not started: M10 MCP tools; test-lock coverage for `docker start/stop`; GUI U2–U5 | manager tracker |
| H8 | Optionally amend the commit author (commits are authored "Claude Code") before merging | — |
| H9 | Merge to the manager's `main` only after H2–H5 pass (the manager is live), then `pipx reinstall llamacpp-manager` | — |

## Steps (on the Mac, in the manager repo)

```bash
cd ~/LocalProjects/GitHubProjectsDocuments/llamaCPPManager   # adjust path
shasum -a 256 ~/Downloads/llamacppmanager-benchmark-support.tgz   # must match the sha256 above
tar xzf ~/Downloads/llamacppmanager-benchmark-support.tgz -C /tmp
git switch main && .venv/bin/pytest tests/ 2>&1 | tail -1          # macOS baseline, record it
git fetch /tmp/llamacppmanager-benchmark-support/feat-benchmark-support.bundle feat/benchmark-support:feat/benchmark-support
git switch feat/benchmark-support
git log --format=%H b7d27f9a71fd7663147168f408a8190d8de1bdea..16484405e3f9e9dc0487867c9c6d8c0ac1b87326                                  # must equal commits 3,2,1 above
git push -u origin feat/benchmark-support                          # now it is safe in the real repo
```

## Prompt for the next agent (paste as the first message)

> Work in `arionrepo/llamacppmanager` on the Mac. Read `CLAUDE.md` and claim files via `queuectl` before editing. Then read `docs/MANAGER_HANDOFF.md` in https://github.com/lballaty/Alt-JEV-LABs. Apply `feat/benchmark-support` from the bundle I provide, verify the three commit hashes listed there, and push the branch. Run the macOS test baseline on `main` first, then on the branch, and report any new failures. Then do H3 (GUI U1), H4 (MLX checklist) and H5 (Mac checklist) from `docs/BENCHMARK-SUPPORT-TRACKER.md`. Record results in that tracker. Do not merge to `main` until those pass; the manager is live.

## Mac handoff evidence to return

Capture complete baseline and candidate test logs and exit codes; the historical `tail -1` examples alone are insufficient. The manager is live: a failing gate is not waived by Alt-JEV-LABs D21 auto-merge policy.

- Claim exact files via the manager's queue before editing; this documentation handoff grants no manager code ownership.
- Verify checksum before unpacking; inspect archive member paths and unpack into a fresh, isolated temporary directory.
- Verify the base object exists, run `git bundle verify`, and fetch the original branch. Check the original tip's ancestry before applying additional fixes.
- Unit tests may use the repository test environment. H4/H5 live verification must use the pipx-installed CLI and configured MLX environment.
- Record CLI executable/version, host hardware/OS, source revision, focused/full test commands, exit codes, and full results.
- Record GUI U1 build/test evidence, MLX manifest/offline/readiness/memory checks, lifecycle suppression and restart regression evidence, and status-JSON compatibility.
- Keep machine-specific inventory, credentials and identifiable traces outside Git; commit a redacted evidence summary and update the manager tracker.
- H2–H5 remain required before manager main merge; H6 remains an owner decision and H7 remains separate incomplete work.

**Current blocker:** this session cannot perform live macOS/MLX/GUI validation. WS9 coordination is complete through delivery verification and a concrete handoff; application and release readiness are not complete.
