# Jev comparability: what is known, what is not, and how we compare

Status: **draft, 2026-10-04, `claude-cloud-ws1-01`. Most items below are UNVERIFIED.** Evidence is marked **Verified** only where it was read directly from a GitHub repository at the commit shown. Everything else came from web-search summaries of secondary pages and must not be quoted as fact. This environment cannot reach `arxiv.org` or `typesafe.ai` (checked 2026-10-04: both blocked by the egress proxy), so the vendor's documentation and the 37-dataset paper have **not been read**.

Intent reminder (`docs/PROJECT_INTENT.md`): we choose the best solution for a concrete decision workflow (alert triage). We do not set out to reproduce a vendor's benchmark, and a favorable synthetic score is not evidence of operational readiness (D26).

## 1. What "Jev" is

- **Jev** (`jev-1.13.x`) is TypeSafe AI's hosted "System One" decision model, reportedly released 2026-09-15 (unverified, search summaries). It returns typed values instead of text: **Choice** (pick one of up to 255 options, with probabilities), **Score** (position on a 2-10 level rubric) and **Noul** (probability a yes/no statement is true). These are the same three primitives as our v1 harness.
- It is **not** a Nous product.
- **Open-Jev** (`zefan-cai/open-jev`) and **SemIf-OpenJev** (`TheoLeeCJ/SemIf-OpenJev`) are independent open reproductions of the interface. They are not TypeSafe Jev. SemIf states it is not affiliated with Jev or TypeSafe.

## 2. Evidence status

| Source | What it is | Status |
| --- | --- | --- |
| `zefan-cai/open-jev` @ `88f2e20` README | Open-Jev-2B/9B/27B results, incl. JevBench public-231 and Hard-111 tables | **Verified (read).** These are Open-Jev model scores, not TypeSafe Jev |
| `dchristopoulos/jev-aita` @ `35bc17e` README | Independent study: Jev vs Sonnet 5, GPT-5 nano and local models on 770 AITA posts; Brier, latency, cost; pins `jev-1.13-20260917`; open code | **Verified (read, README head only)** |
| `AbdelStark/awesome-typesafe-jev` @ `af429b4` | Index of ecosystem projects, incl. `scienthoon/jev-ood-calibration` and `jyatesdotdev/jev-logtriage` | **Verified for the listing text only.** The linked studies themselves were not read |
| arXiv 2609.37647 "Evaluating and Benchmarking the System One Model Jev" (37 public datasets) | Third-party paper per its listing | **Unverified.** Only a search summary; not read |
| Vendor docs (known failure modes, calibration guidance, API contract) | TypeSafe documentation | **Unverified.** Only relayed by secondary articles |
| LiteLLM `jev_classifier.py` | LiteLLM router integration | Path exists (**verified**). The published router benchmark figures were **not found** in a `cookbook/benchmarks/jev-benchmark` directory and are unverified |

## 3. Corrections to circulated claims (checked 2026-10-04)

1. "Jev scores 197/231 (85.28%) and 80/111 (72.07%) on JevBench" is **wrong as stated**. Those are **Open-Jev-27B-v1.1** numbers. The same table lists Open-Jev-2B at 150/231 (64.94%) and 9B at 179/231 (77.49%).
2. The command `cd open-jev/benchmarks && python run_jevbench.py --model typesafe:jev-1.13.0 --tasks public_231 --audit-replay` does **not exist**: that repo has no `benchmarks/` directory, no `run_jevbench.py`, no `--audit-replay` and no `public_231`. The pinned benchmark commit `f8ce71361165846101d02ebc83ad44e47ae44fc3` is real but belongs to `fstandhartinger/jevbench`; open-jev provides `scripts/run_jevbench_suite.py` and `scripts/run_jevbench_hosted.py`. Its README says the 231 tasks are the public subset of 534 and no full-534 score is claimed.
3. Latency, ECE and accuracy "targets" circulated for Jev, local SLMs and hosted LLMs are **unsourced** and partly conflict (independent tests reported ECE around 0.16, circulated figure 0.071). **Never use them as pass thresholds** (`AGENTS.md` rule 1).
4. The endpoint, request JSON and size limits (255 options, 10 levels, 32k/64k tokens) are **unverified**. Read the vendor docs before writing an adapter (`AGENTS.md` rule 8).

## 4. Why published numbers cannot be compared with ours

Published tests are mostly generic public benchmarks. Ours is domain-specific alert triage under a frozen rubric. Comparable numbers need the vendor's dataset list and splits, per-dataset templates, metric definitions (ECE bins, Brier weighting), comparator setup, model version, request settings and timing method. We hold **none** of these from a primary source.

## 5. How we make the comparison valid instead

- **Route B (primary): run Jev as a hosted arm on our own v2 cases.** Every candidate sees the same cases, context and contract. Comparability comes from our protocol, not theirs.
- **Route A (optional anchor): run alternatives on a few public datasets Jev's paper used, with its templates.** Only after the paper's protocol is read. A sanity check, not the goal.

### Requirements for the hosted Jev arm (owner approval in principle, D29; details to confirm)

- Mark it **hosted/remote** in every report; an explicit, labeled exception to the local-only rule (`AGENTS.md` rule 4).
- Send **synthetic cases only**. Never real, de-identified or local-only-seed text (D26, D28).
- API key from the environment, never committed or logged. Spend limit set by the owner.
- Record the **exact model version string returned per response** (the gateway may drift; one independent study notes versions were not always exposed), request settings and timing method.
- Count network errors and refusals separately from wrong answers (`AGENTS.md` rule 8).
- Adapter written from the vendor's primary documentation, not from this file.

### Test-design changes this implies (not yet built)

1. **Page-now threshold tuned on validation.** The WS4 scorecard currently assumes a fixed P >= 0.5. A circulated finding (paper summary, unverified) says binary probabilities rank well but sit badly against a fixed 0.5.
2. **Negative-control sets:** date/interval reasoning (maintenance and change windows), counting (burst sizes) and long irrelevant input. These are vendor-listed weaknesses (unverified) and gaps in our cases.
3. **Abstain output and a risk-versus-coverage curve** (selective prediction); the model contract has no abstain output today.
4. **Question-batching comparison:** all three questions in one call versus one call each. The runner currently makes one call per task.
5. **Already covered:** injected-instruction text (cohort B').
6. **Same-context symmetry:** every candidate receives the same truncated context.

## 6. Not verified, and how to close it

- Read arXiv 2609.37647 and the vendor docs. Options: owner widens the environment network allowlist to `arxiv.org` and `typesafe.ai`; owner pastes the relevant sections; or the Mac agent fetches them.
- Read `jev-ood-calibration` (unseen priority rule, 900 synthetic tickets) and `jev-logtriage` (same use case) in full; both are on GitHub.
- Confirm the LiteLLM benchmark location and figures, if they exist.
- Resolve the `jev-1.13.0` versus `jev-1.13-20260917` naming.
