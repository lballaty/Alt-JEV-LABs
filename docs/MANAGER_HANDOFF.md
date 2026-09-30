# Handoff: llamaCPPManager benchmark-support work

Status: **Implemented and tested on Linux; not yet in `arionrepo/llamacppmanager`.** The authoring session had read-only access to that repo, so the work was delivered as a file. This document contains **no manager code**. It is the checklist that makes sure everything lands in the manager repo.

## Where the work is

| Item | Value |
| --- | --- |
| Delivery file | `llamacppmanager-benchmark-support.tgz` (attached in the authoring chat, 2026-09-30). Contains `feat-benchmark-support.bundle`, `patches/0001–0003`, `APPLY.md` |
| tgz sha256 | `7e083c6821f454a9648f6a2c44f7f1d1e5f0e88e4c974118a8619833e870733b` |
| Base commit | `b7d27f9a71fd7663147168f408a8190d8de1bdea` (VERSION 2026.09.10.2) |
| Branch | `feat/benchmark-support` |
| Commit 1 | `22c419727015b92930bc03e9c3c472983f8f81f5`: docs+deps: benchmark support tracker; pin mcp<2 (M0) |
| Commit 2 | `19dde33f172e9b4e4211496c84a75d4e5ad81eef`: feat: opt-in benchmark support |
| Commit 3 | `16484405e3f9e9dc0487867c9c6d8c0ac1b87326`: docs: GUI impact, auto-restart rationale, MLX verification plan |
| Size | 17 files, +1592 / −4 lines vs base |
| Linux result | 181 passed / 6 failed / 3 skipped. The 6 are the same macOS-only failures as the baseline (160 passed / 6 failed) |

After applying, `git log` on the branch must show exactly these three hashes. If it does, nothing was lost or altered.

## What is still to do in the manager repo

| # | Work | Where it is specified |
| --- | --- | --- |
| H1 | Apply the bundle and verify the hashes (steps below) | `APPLY.md` in the tgz |
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
git log --format=%H b7d27f9..HEAD                                  # must equal commits 3,2,1 above
git push -u origin feat/benchmark-support                          # now it is safe in the real repo
```

## Prompt for the next agent (paste as the first message)

> Work in `arionrepo/llamacppmanager` on the Mac. Read `CLAUDE.md` and claim files via `queuectl` before editing. Then read `docs/MANAGER_HANDOFF.md` in https://github.com/lballaty/Alt-JEV-LABs. Apply `feat/benchmark-support` from the bundle I provide, verify the three commit hashes listed there, and push the branch. Run the macOS test baseline on `main` first, then on the branch, and report any new failures. Then do H3 (GUI U1), H4 (MLX checklist) and H5 (Mac checklist) from `docs/BENCHMARK-SUPPORT-TRACKER.md`. Record results in that tracker. Do not merge to `main` until those pass; the manager is live.
