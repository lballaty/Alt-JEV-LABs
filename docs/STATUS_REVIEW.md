# Status review: intent, evidence, implications and open decisions

Living review. Written 2026-10-05 by `claude-cloud-ws1-01` at the owner's request. It reviews the lab against the owner's intent and the companion ebook. Anything marked **suggestion** is not adopted until the owner confirms it (D31). Facts about Jev come from `docs/JEV_SOURCES.md`; pins and hashes are in `docs/references/jev_sources.json`.

## 1. Intent (owner statement, D33)

Two parallel deliverables:

1. **Alt-JEV-LABs (this repo):** test alternatives to Jev and show the results, honestly scoped (synthetic-only results compare models; they do not approve deployment, D26).
2. **The ebook, *The Deterministic Edge*, with a companion code repository:** explains in plain English, not jargon, **how to set up and use Jev or the alternatives** in the selected use case (operational alert triage), including potential implementations and a relevant example with code. The ebook is **not** a results report.

All testing runs from the owner's M4 Max Mac.

## 2. What exists (Linux-verified; no model run, nothing run on the Mac)

| Area | State |
| --- | --- |
| Rubric 2.4.0 | Frozen; 60 rubric tests |
| Seeds | 322 Loghub templates + 8 Atomic Red Team commands committed; 40 vendor-licensed templates reference-only (fetched locally, never committed) |
| Cohort generator | 560 synthetic cases (A 200, B 125, B' 60, C 100, D 75); splits 394/83/83; leak lint |
| Chat module | Optional, off by default |
| Runner, scorecard, report (WS4) | Merged; gates return pass / fail / inconclusive / not evaluated |
| Jev source library | 4 papers, official SDKs, independent studies; pinned and summarised |
| Tests | 289 passing on Linux |

Not built: adapters retargeted to six routes and P1-P4 (WS8, released to the Mac agent), leave-one-source-out splits, stream replay, label-budget subsets, network-path field in the runner (D32), any hosted Jev adapter, anything for the ebook's example code.

## 3. Implications of the evidence gathered

1. **Published Jev results cannot be placed beside our scorecard.** They cover public benchmarks, not alert triage, and some may be inflated by training exposure (the 37-dataset paper's own caution). Only latency and cost are citable, with their network conditions.
2. **Every published Jev latency includes a network trip** (Jev is cloud-only). Independent measurements cluster at about 0.3-0.4 s from Europe, Brazil and UTC+3; the vendor quotes 70-500 ms end to end. Our local candidates have no network. D32 requires labelling each latency's network path and measuring network delay separately.
3. **Our synthetic cases cannot be in anyone's training data**, which is an advantage over public benchmarks; 294 of 560 use templates we wrote, which limits realism.
4. **A fixed 0.5 page-now threshold is likely unfair to probability models** (two papers; also TypeSafe's own guidance to set thresholds on your data). Our WS4 scorecard uses P >= 0.5. **Suggestion:** tune on validation.
5. **The test split is small** (83 cases, 9 B'), so most gates will be inconclusive. Published studies hit the same limit.
6. **The `event.signal` field nearly names the event type**, favouring keyword matching for every candidate (WS4 flag).
7. **Context limits look fine:** rendered cases average about 516 characters (max 962), roughly 150-300 tokens, inside Laya English's reported 512-token cap. Recheck with final question text on the Mac.
8. **The official SDKs define Jev's API exactly** (endpoint, request, response, errors), so an adapter and the ebook's how-to code can be written against primary sources. They do not state limits or pinned version names.

## 4. If Jev were tested from the M4 Max (suggestion; D31 keeps it out of phase 1)

Jev cannot run on the Mac. "Same environment" can mean the same client machine, cases, harness, timing method and session; it cannot remove the network trip. Per D32, time a free call to the same host (`GET /v1/models`) through the run and report Jev end to end and with the round trip separated.

| Run | Requests | Tokens (estimate) | API cost at USD 0.042 per million input tokens |
| --- | --- | --- | --- |
| 560 cases, three questions | 560 (combined) to 1,680 (separate) | up to 1.7 M | up to USD 0.07 |
| Three repeats for run-to-run variance | up to 5,040 | up to 5 M | up to USD 0.21 |
| Timing, 5 sessions x (20 untimed + 500 timed) | 2,600 | up to 2.6 M | up to USD 0.11 |
| **Total with 10x margin** | about 7,600 | up to 8 M | **under USD 5** |

Token estimate: about 1,000 tokens per case (no Jev tokenizer available; the 37-dataset paper averaged 630 per request). Price per the 37-dataset paper and InfoQ, not confirmed with TypeSafe. Other costs: a small prepaid account top-up (unverified), one adapter with tests, about 45 minutes of sequential timed calls on the Mac, and owner approvals: an exception to the local-only rule (`AGENTS.md` rule 4) with synthetic data only, a spend limit, and a reading of TypeSafe's customer terms first (they may contain a non-compete clause like the one on the Zenodo responses, Q11).

## 5. Alignment with the ebook (read from the private publishing workspace, `searchingfool-publishing` @ `1e4eb07`)

Owned by `codex-ebook-companion-01`. Findings, for the owner and that agent:

1. **The proposed outline is mainly about evaluation method, not setup.** It proposes a "Requirements-Evidence-Judgment" method across ten chapters (decision contract, evidence, judgment, reproduction, extension, pilot). The owner's stated intent (D33) is a plain-English guide to **setting up and using Jev or the alternatives** in the triage example, with code. These overlap but differ in emphasis; the outline has no chapter on calling Jev or running a local alternative. **Suggestion:** owner to confirm which emphasis governs before chapters are drafted.
2. **The companion repository does not exist yet.** The plan names `SearchingFool/deterministic-edge`; creation is pending. The example code (a triage service that calls Jev or a local model and applies deterministic rules) is not built anywhere; the brief calls this runtime `edge-triage-gateway` and leaves its location open. This repo does not build it (`docs/PROJECT_INTENT.md`).
3. **What this lab can supply to the ebook:** the decision contract (rubric 2.4.0), synthetic example cases, the evaluation method and harness, verified facts about Jev's API (official SDKs), and, once measured, versioned results with limits.
4. **What the ebook still needs that nobody owns:** plain-English setup code for (a) calling Jev with the official SDK, (b) running a local alternative on a Mac, (c) the deterministic policy layer that decides actions, in one small runnable example. Section 5a shows a plausible shape: one client, swappable endpoint, gate table in code.
5. **The ebook tracker lists "exact JEV comparison source unverified".** That is now resolved for API facts by the official SDKs in `docs/JEV_SOURCES.md`.

## 5a. What the alert-triage examples add (from `docs/JEV_SOURCES.md`)

1. **One client code path for Jev and local alternatives is feasible.** TypeSafe's official SDK reads its base URL from `TYPESAFE_BASE_URL`, and two open projects serve the same `POST /v1/systemone` request shape locally: `jevmlx` (MIT, Apple Silicon MLX) and Simple Jev (Apache-2.0). **Suggestion for the ebook example:** the same triage code calls Jev or a local model by changing one setting. Caveats: jevmlx downloads weights on first use (conflicts with our no-download rule unless pointed at manager-provisioned weights), and neither project's accuracy is verified.
2. **Spoofed text is a demonstrated weakness**, not a hypothetical: jevgrep reports a self-labelling "SYSTEM NOTE TO AI FILTERS" line scoring 0.97. This supports keeping cohort B' and the policy layer's refusal to act on claims inside alert text.
3. **Trusted context changes results:** jev-sec-bench reports recall rising from 74.9% to 95.1% when deployment context is added. **Suggestion:** an ablation with and without the context block.
4. **jev-logtriage is the closest existing example** to the ebook's use case, and its design (typed questions, then a gate table in code that prints its reason) is a good teaching template. It lacks trusted context, spoof handling and an evaluation, which is exactly what the lab adds.
5. **No public project reports false pages or missed P1s.** Our scorecard's separate must-page and false-page reporting fills a real gap.

## 5b. What the alternative-model repositories add (from `docs/JEV_SOURCES.md`)

1. **Three alternatives already serve Jev's exact request format locally** (upstream Laya, Von, Decider), and two more open servers do too (jevmlx, Simple Jev). This makes a single test harness and a single ebook example code path realistic.
2. **Defaults that would make a test unfair if left alone:** Von's default Noul is a banded value, not a probability; Von runs chains by default; GLiClass silently uses CPU unless given a `torch.device`; Laya's multilingual model has no fitted temperatures. These must be set explicitly and recorded.
3. **Our own Laya route is unpinned** (`configs/benchmark_config.yaml` and `models/laya_runner.py` pass no revision). This violates our provenance rule; `models/*` is released to the Mac agent (D27), so it is listed for WS8.
4. **Blueprint corrections (suggestions):** SemIf has no Score; Decider is missing from the candidate matrix; upstream Laya's own figures say the base checkpoints are weak and only a fine-tuned checkpoint is competitive.
5. **Context:** GLiClass truncates silently at its default 1,024 tokens; Laya English is 512. Our cases appear to fit; the runner must still mark over-length inputs unsupported.

## 6. Does the work make sense?

- **The lab is aligned with "test alternatives to Jev and show results"**, with one gap: phase 1 compares local alternatives with each other and shows Jev only through published figures that are not comparable on accuracy (D31). The results can say how alternatives perform on alert triage and what Jev's published latency and cost are; they cannot say which is more accurate on alert triage unless Jev is run on our cases (section 4).
- **The research was needed but should now stop** (owner, 2026-10-05). Remaining unread sources are low value except the vendor docs pages, which the official SDKs largely replace.
- **The biggest open risk is not in the lab but between the lab and the ebook:** no one is building the how-to example code, and the outline emphasis differs from the stated intent.

## 7. Decisions needed from the owner

| # | Decision | Why |
| --- | --- | --- |
| 1 | Q1-Q3, Q8: which local candidates, and where their checkpoints are stored | Blocks the Mac run |
| 2 | Q4: latency budget; confirm memory cap and reserve | Scorecard gate |
| 3 | Page-now threshold: fixed 0.5 or tuned on validation (suggestion) | Fairness to probability models |
| 4 | Q10: which published Jev figures to cite | Phase 1 reporting |
| 5 | Phase 2 hosted Jev arm: yes or no (section 4) | Only route to an accuracy comparison on our task |
| 6 | Ebook emphasis: setup guide (D33) versus evaluation method (current outline) | Before chapter drafting |
| 7 | Who builds the ebook's example code, and where (companion repo) | Unowned today |
| 8 | Edit `AGENTS.md` rule 6 to match D21 | Agent instructions conflict |
| 9 | Q11: Zenodo Jev responses' non-compete clause | Only if those responses are ever used |
| 10 | Add Decider to the candidate matrix; mark SemIf as Choice-only (suggestions, 5b) | Candidate list for Q3 |

## 8. Research status

Complete for now (owner instruction, 2026-10-05). All three read-only research tasks reported: official SDKs (section 3 item 8), alert-triage examples (5a), alternative models (5b). Remaining unread: TypeSafe's docs site and customer terms (blocked here), the Zenodo responses (not needed; Q11).
