# Jev comparability: what is known, what is not, and how we compare

Status: **draft, 2026-10-04, `claude-cloud-ws1-01`. Most items below are UNVERIFIED.** Evidence is marked **Verified** only where it was read directly from a GitHub repository at the commit shown. Everything else came from web-search summaries of secondary pages and must not be quoted as fact. This environment cannot reach `arxiv.org` or `typesafe.ai` (checked 2026-10-04: both blocked by the egress proxy), so the vendor's documentation and the 37-dataset paper have **not been read**.

Intent reminder (`docs/PROJECT_INTENT.md`): we choose the best solution for a concrete decision workflow (alert triage). We do not set out to reproduce a vendor's benchmark, and a favorable synthetic score is not evidence of operational readiness (D26).

Source pins, hashes and what was read: `docs/JEV_SOURCES.md` and `docs/references/jev_sources.json`.

> **Owner decision D31 (2026-10-05): phase 1 does not test Jev ourselves. Jev is represented by its published figures (including published latency).** Everything in sections 5-8 below that would change the plan (a hosted Jev arm, new test sets, new metrics, new partitions, measuring Jev latency) is a **suggestion only** and is not adopted unless the owner confirms it.

> **Owner decision D32 (2026-10-05):** every latency we report states whether it was on-device, local loopback or remote, and network delay is measured separately where possible.

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
| arXiv 2609.33401 "Evaluating System One Models for Agent Security Decisions" (Y. Liu, TraceStone/NTU; preprint, 27 pages) | Independent study of Jev 1.13 (hosted), Laya, Decider, Nimble vs LLM judges and specialist classifiers on R-Judge, AgentHarm, WAInjectBench | **Verified (full text read from the PDF supplied by the owner, 2026-10-05).** Not peer reviewed; states OpenAI Codex assisted with design and code. Artifact repo named: `github.com/yxsec/system-one-security-eval` (not yet read) |
| arXiv 2609.37647 "Evaluating and Benchmarking the System One Model Jev" (37 public datasets) | Independent academic evaluation (Bonn / Lamarr / Fraunhofer IAIS), code and responses released | **Verified (read from owner-supplied PDF and its code repo, 2026-10-05).** See `docs/JEV_SOURCES.md` |
| Vendor docs (known failure modes, calibration guidance, API contract) | TypeSafe documentation, probably `https://docs.typesafe.ai/introduction` | **Unverified.** URL seen in a third-party README; not opened. Only relayed by secondary articles |
| InfoQ release article | News piece reporting vendor figures, third-party measurements and developer comments | **Read from owner-pasted text only; unverified.** Corroborates the 32k context window, version pinning, and the documented weaknesses |
| LiteLLM `jev_classifier.py` | LiteLLM router integration | Path exists (**verified**). The published router benchmark figures were **not found** in a `cookbook/benchmarks/jev-benchmark` directory and are unverified |

## 3. Corrections to circulated claims (checked 2026-10-04)

1. "Jev scores 197/231 (85.28%) and 80/111 (72.07%) on JevBench" is **wrong as stated**. Those are **Open-Jev-27B-v1.1** numbers. The same table lists Open-Jev-2B at 150/231 (64.94%) and 9B at 179/231 (77.49%).
2. The command `cd open-jev/benchmarks && python run_jevbench.py --model typesafe:jev-1.13.0 --tasks public_231 --audit-replay` does **not exist**: that repo has no `benchmarks/` directory, no `run_jevbench.py`, no `--audit-replay` and no `public_231`. The pinned benchmark commit `f8ce71361165846101d02ebc83ad44e47ae44fc3` is real but belongs to `fstandhartinger/jevbench`; open-jev provides `scripts/run_jevbench_suite.py` and `scripts/run_jevbench_hosted.py`. Its README says the 231 tasks are the public subset of 534 and no full-534 score is claimed.
3. Latency, ECE and accuracy "targets" circulated for Jev, local SLMs and hosted LLMs are **unsourced** and partly conflict (independent tests reported ECE around 0.16, circulated figure 0.071). **Never use them as pass thresholds** (`AGENTS.md` rule 1).
4. The endpoint `api.typesafe.ai/v1/systemone` and the size limits (255 options, 10 levels, 64k tokens combined) are **unverified**. A 32,000-token context window is reported by the InfoQ article. The independent study in `arXiv 2609.33401` reached Jev through OpenRouter's decisions endpoint with model `typesafe/jev-1.13` (see `docs/JEV_SOURCES.md`). Read the vendor docs before writing an adapter (`AGENTS.md` rule 8).

## 4. Why published numbers cannot be compared with ours

Published tests are mostly generic public benchmarks. Ours is domain-specific alert triage under a frozen rubric. Comparable numbers need the vendor's dataset list and splits, per-dataset templates, metric definitions (ECE bins, Brier weighting), comparator setup, model version, request settings and timing method. We hold **none** of these from a primary source.

## 5. Suggestions for a later phase (not adopted; owner confirmation required)

- **Suggestion, route B: run Jev as a hosted arm on our own v2 cases (not in phase 1, per D31).** Every candidate sees the same cases, context and contract. Comparability comes from our protocol, not theirs.
- **Route A (optional anchor): run alternatives on a few public datasets Jev's paper used, with its templates.** Only after the paper's protocol is read. A sanity check, not the goal.

### If a hosted Jev arm is ever approved, it would need (suggestion)

- Mark it **hosted/remote** in every report; an explicit, labeled exception to the local-only rule (`AGENTS.md` rule 4).
- Send **synthetic cases only**. Never real, de-identified or local-only-seed text (D26, D28).
- API key from the environment, never committed or logged. Spend limit set by the owner.
- Record the **exact model version string returned per response** (the gateway may drift; one independent study notes versions were not always exposed), request settings and timing method.
- Count network errors and refusals separately from wrong answers (`AGENTS.md` rule 8).
- Adapter written from the vendor's primary documentation, not from this file.

- **Pin an explicit model version** (for example `jev-1.13.0`); never the moving `jev-latest` or `jev-preview` aliases. Cost is low per the vendor (USD 0.042 per million input tokens, output free), so a full run on our synthetic cases should be cheap, but confirm pricing from the vendor page before the owner sets a spend limit.
- Look for the vendor's **System One adapter** (said to run other models against the same schema); read its documentation before deciding how to normalise the other candidates.

### Suggested test-design changes (not adopted; owner confirmation required)

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

## 7. What arXiv 2609.33401 verifies (read in full)

Setup it documents (useful as a design template, not as numbers to match): fixed partitions (development for recalibration, selection for thresholds, confirmation, test); groups of related inputs kept in one partition; original labels excluded from model inputs; identical task question and label definitions for every model; inputs over a model's context limit marked **unsupported, not truncated**; paired 95% cluster bootstrap (2,000 resamples) with Holm correction; Brier, NLL, ECE (10 equal-width bins, with 5 and 20 bins as sensitivity), AUROC, AP; Jev 1.13 via hosted API; Laya pinned English checkpoint on CPU/float32; temperature scaling fitted on development data only.

Findings that bear on our tests (this paper's tasks are agent security, not alert triage; they may not transfer):

1. **A high aggregate rank can hide a missed attack group.** Jev missed all 129 attack inputs without explicit instructions while flagging one benign input. We already report per cohort; keep it.
2. **ECE can look good while separation is poor.** Laya's R-Judge ECE was lower than Jev's under some binnings, yet its AUROC was 0.487 vs 0.963 and its Brier was worse than a constant-probability baseline. Report AUROC and Brier against a base-rate baseline next to ECE, and ECE at 5/10/20 bins.
3. **Strict miss limits leave little to automate.** At a 1% unsafe-miss limit, Jev automated 0% of WAInjectBench and 7.63% of R-Judge (17 blocks, 1 allowance). Two-threshold policies (allow / block / escalate) raised coverage mainly by blocking more. We have no coverage-under-error-budget measure; add one.
4. **Thresholds that pass validation can fail on test.** Hence a separate confirmation partition. Our split has only train/val/test (83 val cases), so calibration and thresholds share one thin set.
5. **Recalibration can hurt.** Development-fitted temperature scaling lowered Jev's WAInjectBench NLL (1.131 to 0.374) but raised its Brier and ECE; on AgentHarm (T=0.05) it raised NLL from 0.481 to 2.163. Always report raw and calibrated arms separately (we do).
6. **The decision component itself can be attacked.** The paper cites work on injection that flips Jev's choices, and a finding that Jev, Laya and Open-Jev can follow option-name semantics instead of the definitions bound to them. Add an option-renaming ablation (swap or obscure option names while keeping definitions).
7. **Hosted models drift:** the same model name need not reproduce the same results. Record the version string per response (already required above).
9. **Probabilities are quantised and use exact 0/1** (`jev-ood-calibration`): decide and record how exact zeros are floored in log-loss, since the choice can drive a temperature fit.
10. **Familiar-task calibration does not transfer to unseen rules** (`jev-ood-calibration`: 44.7% accuracy with mean stated probability 0.74 on an organisation-specific priority rule). Keep held-out wrapper families and B' as hard gates.
8. **Small samples dominate.** A 1% miss limit needs zero misses among 74 unsafe selection inputs. Our 83-case test split has the same problem; keep reporting counts and intervals.

Where our plan already matches: grouped splits, paired comparisons, label-free inputs, identical context, per-cohort results, raw-vs-calibrated arms, no deployment claims.

Suggestions from this paper (not adopted; owner confirmation required): confirmation partition or a documented reason not to split further, coverage-under-error-budget with an escalate band, AUROC/AP and Brier-vs-constant baseline, ECE bin sensitivity, option-name ablation, unsupported-not-truncated rule check in the runner.

## 8. What arXiv 2609.28940 and 2610.01079 add (observations and suggestions only)

Neither is strong evidence (a one-run case study and a preprint whose abstract and body disagree on the comparison model and sample size), but both sharpen our design:

1. **Published latency for Jev varies widely** (vendor 70-500 ms; 236-276 ms p50 in one paper; 310-335 ms mean in another; user-reported median 76 ms), depending on location, payload and method. Phase 1 uses published figures (D31); **which published figure, or range, to cite is an open question for the owner (Q10)**.
2. **Context caps.** The English Laya checkpoint is reported at 512 tokens. The runner must classify over-length inputs as unsupported (not truncate) and report coverage; check our case lengths against each candidate's cap before the Mac run.
3. **Fail-open versus strict.** One paper counts no-output calls as benign. Keep our strict forms and report the lenient form separately only if needed.
4. **Label-budget arm.** A few-shot (k examples per class) arm for generative candidates, next to Jev's no-training mode and Laya's trained heads, is a fair way to compare label needs. This is already planned as S7 and remains unbuilt.
5. **Asymmetric failure.** A decision layer that suppresses real events can be worse than none. Keep must-page recall and B' escalation-kept as hard gates, and report disagreements with a baseline.
6. **Data residency.** Jev is cloud-only; any hosted-arm use must respect the synthetic-data-only rule above.

## 9. What arXiv 2609.37647 settles (observations; suggestions need owner confirmation per D31)

Corrections to circulated claims, now checked against the paper:

- Banking77: **79.7%** (circulated "74-77%"; the pentest paper quoted 0.870, both unsupported by this source).
- AG News: **88.5%** (circulated "ceiling around 86%"; pentest paper 0.910).
- ECE: pooled Choice ECE **0.028**; mean over 33 datasets **0.074**; per-dataset values range up to 0.279 (Emotion). The circulated "median 0.071" is close to the per-dataset mean, not a median; the pentest paper's 0.246 and blog figures of about 0.16 come from other task sets.
- Published latency in this study: **0.36 s mean per request, client-side, 32 concurrent, including network**. Add this to the Q10 candidates.

Observations relevant to phase 1 (published figures only):

1. Published Jev numbers are for general public benchmarks, not alert triage, and some may be inflated by training exposure (the authors' own caution). Any report citing them should say so.
2. The paper's binary-threshold finding (0.5 often a poor operating point; tuned thresholds help) and its multi-label over-prediction finding are the published facts most relevant to our page-now (Noul-like) question.

Suggestions (not adopted):

- If a later phase compares other candidates with Jev, the paper's method (identical requests; options as single-token codes; exact option probabilities from one forward pass; Jev-style confidence formula) is a ready, published way to make generative candidates comparable without text generation. The MIT-licensed harness could be studied for this.
- Do not download or use the Zenodo Jev responses until the owner decides whether their "no competing product" clause affects this project.
