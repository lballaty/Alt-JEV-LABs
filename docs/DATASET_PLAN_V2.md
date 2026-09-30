# v2 dataset sources and test structure (plan)

Status: **Draft / proposed — not implemented, not measured.** Companion to `docs/BLUEPRINT_V2.md` (branch `feat/finite-json-calibration`), which already fixes the 500-case pilot, the four cohorts, the five v2 routes and the boundary-label caveat. This file decides *where seeds come from*, *what each cohort must contain to be a fair test*, and *how work is split so it can run in parallel*.

## 1. Seed sources — verification status (checked 2026-09-30)

| Source | Verified here | License / terms | What it actually provides | Decision |
| --- | --- | --- | --- | --- |
| Loghub (`logpai/loghub`) | ✅ cloned | "Freely available for research or academic work"; any use or distribution must reference the repo URL and cite the paper | Per-system `*_2k.log`, `*_structured.csv`, `*_templates.csv` in-repo (OpenSSH 27, OpenStack 43, BGL 120, HDFS 14, Linux 118 templates). Full logs on Zenodo. Only BGL/HDFS/OpenStack carry anomaly labels (normal/anomaly), not route/score. | **Use templates only** (`<*>` placeholders), filled with synthetic entities. Do not vendor raw `.log` lines: OpenSSH samples contain real public IPs and usernames (AGENTS.md rule 4). |
| OpenEnv SRE triage (`DarDrax/incident-triage-env`, HF) | ❌ huggingface.co blocked by this environment's egress policy | Unverified | Unverified | **Excluded until verified** on a host with HF access (existence, license, content). Not a dependency of the pilot. |
| Atomic Red Team (`redcanaryco/atomic-red-team`) | ✅ repo page | MIT | Test *definitions and command lines*, mapped to ATT&CK IDs — not captured telemetry | Use command lines + technique IDs as seeds; wrap them in synthetic process/auth log lines. Record technique ID per case. |
| MITRE ATT&CK | not fetched | ATT&CK terms of use (attribution) — confirm before redistribution | Technique taxonomy | Use technique IDs/names as metadata only. |

Consequence for the proposal text: Loghub labels are *anomaly/normal*, so "directly maps system error levels to our enum" is **our rubric applied to real syntax**, not upstream ground truth. Reports must say so.

## 2. Contract alignment (needs decision)

The proposal uses `service_outage`; BLUEPRINT_V2 routes are `routine_audit`, `policy_exception`, `security_escalation`, `data_sovereignty_flag`, `telemetry_heartbeat`. Storage timeouts and "proxy is toast, 502s" (Cohorts A and C) have no home in the v2 set. Options:

| Option | Effect |
| --- | --- |
| Add `service_outage` as a 6th route | Matches the proposal; rubric and precedence must define outage vs security overlap |
| Keep 5 routes; outages → `policy_exception` | Keeps blueprint; semantically weak, inflates one class |
| Keep 5 routes; drop outage seeds (HDFS/BGL) | Loses the most realistic Loghub material |

Noul is a binary proposition ("requires immediate human review?"). Targets like `p ≥ 0.90` / `p = 0.50` in the proposal are **model-output expectations, not labels**; the label is `true`/`false`, plus an `adjudication` field for Cohort D.

## 3. Cohort design — changes required for a fair test

| Cohort | Pilot n | Keep | Change |
| --- | ---: | --- | --- |
| A Direct | 200 | Real template syntax, synthetic entities | Record `seed_source`, `template_id`, `attack_technique` per case |
| B Negation / scope inversion | 125 | Minimal pairs with a Cohort A parent in the same split group | **Add B′ "spoofed authorization"** (see below). Hold out whole *wrapper families* (CR-, chaos, drill) for test, not just new CR numbers |
| C Jargon | 100 | Slang → strict target | Keep the slang lexicon versioned; hold out some slang terms from train |
| D Boundary | 75 | Low-signal events | Label via documented adjudication (≥2 independent reviewers or explicit `needs_adjudication`); report agreement/abstention, not ECE against an invented 0.50 |

**Why B′ is mandatory.** As written, Cohort B teaches that log text saying "Authorized by CR-1234" or "ignore alerts and do not page SOC" should *lower* severity. That text lives inside attacker-controllable payloads, so a model trained only on B learns a prompt-injection bypass. B′ pairs the same wrappers with evidence the authorization is invalid (CR for a different host, expired window, drill announced by an unknown principal, "do not page SOC" appended to a live auth burst) and keeps the escalation label. Report B and B′ accuracy together; a model that wins B by ignoring content should lose B′. This also enforces AGENTS.md rule 5: authorization is verified by the deterministic layer, never inferred from payload text.

**On the "BM25 near 0% on Cohort B is proof" claim.** Don't use that framing. It is a hypothesis, and it conflicts with AGENTS.md ("comparative evidence, not a favorable demonstration"). BM25 retrieves labeled training examples. If B-style wrappers appear in train, BM25 can match them lexically and may score well. The fair test is held-out wrapper families + B′. Whatever BM25 scores there is the result.

Suggested pilot split (from 500): cohort shares as proposed, reserve ~10% of total as B′ taken proportionally from A/B budget, or grow the pilot to ~560. Needs decision; the blueprint's 70/15/15 grouped split applies either way.

## 4. Test structure

```mermaid
flowchart LR
  S[Seed registry<br/>Loghub templates · ART commands<br/>sha256 + source + license] --> G[Cohort generator<br/>A · B · B′ · C · D<br/>seed=42]
  R[Versioned rubric<br/>routes · precedence · score anchors] --> G
  G --> M[Grouped split<br/>by pair_id + template/wrapper family]
  M --> TR[train] & VA[val] & TE[test sealed]
  TR --> FIT[train heads / BM25 index]
  VA --> CAL[calibration + thresholds]
  TE --> RUN[benchmark runner]
  RUN --> REP[report: cohort × primitive × route<br/>n, CI, coverage, N/A]
```

Report matrix (every cell carries numerator/denominator):

- **Rows:** candidate × arm (raw / calibrated; prompt-JSON / finite-JSON).
- **Column groups:** Cohort A, B, B′, C, D, pooled; within each, Choice acc, Noul acc, Score MAE, paired-inversion acc, schema-failure, exception, coverage.
- **Separate tables:** latency (p50/p95, per blueprint timing protocol); calibration (val and test Brier/ECE with bin counts, pooled only — cohort-level ECE on ~11–30 cases is not reportable).
- **Leakage tests (CI):** no `pair_id`, template family, wrapper family or held-out slang term crosses splits; every split has all routes × primitives; manifest hashes match files.

## 5. Parallel workstreams

| WS | Scope | Files (new unless noted) | Blocked by | Can start now |
| --- | --- | --- | --- | --- |
| WS1 Seed registry | Script that pins Loghub commit, extracts `*_templates.csv` for OpenSSH/OpenStack/BGL/HDFS/Linux + ART command seeds, writes `data/seeds/registry.jsonl` with source, license, sha256; synthetic entity filler (RFC 5737 IPs, fake hosts/users) | `data/seeds/`, `data/seed_registry.py`, `tests/test_seed_registry.py` | — | ✅ |
| WS2 v2 rubric | Route definitions, precedence, score anchors, Noul proposition, adjudication protocol | `configs/domains/v2_rubric.json`, `docs/RUBRIC_V2.md` | Decision §2 | after decision |
| WS3 Cohort generator | A/B/B′/C/D generators, grouped splitter, manifest, leakage tests | `data/generator_v2.py`, `tests/test_generator_v2.py` | WS1, WS2 | stub against interfaces |
| WS4 Report matrix | Cohort-aware metrics and CIs in runner/reporter | `evaluation/*` (modified) | Other agent's branch merge (conflict risk) | ❌ wait |
| WS5 Source verification | Verify OpenEnv dataset, ATT&CK terms, and alternative telemetry sources (e.g. OTRF Security-Datasets) on a host with HF access | docs only | HF egress | on Mac / allowlist |

The other agent's branch (`feat/finite-json-calibration`) modifies `data/synthetic_generator.py`, `evaluation/*`, `training/calibrate.py`, `models/*`. WS1–WS3 only add new files, so they don't conflict. WS4 waits for that branch to merge.

## Assumptions

- The v1 generator and dataset stay intact; v2 is a separate dataset/config (per blueprint).
- Loghub's research-only terms fit this work. If the results feed commercial or marketing material, confirm the license first.

## Review flags

- Label set (§2) and B′ budget (§3) need an owner decision before WS2/WS3 freeze.
- Loghub license scope vs intended publication.
- OpenEnv source is unverified and excluded.
