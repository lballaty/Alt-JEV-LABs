# Jev source library (what we read, where it is, what we took)

Recorded 2026-10-05 by `claude-cloud-ws1-01`. Machine-readable pins and hashes: `docs/references/jev_sources.json`. Purpose: stop re-searching. **No third-party text, code, prompts or predictions are copied into this repository.** Facts below are in our own words, with the source and pin that supports each.

## Where the raw copies are

The cloud container is ephemeral: anything stored there is lost when the session ends. Durable storage is therefore (a) this repo, for our own notes, and (b) the pins and hashes in `jev_sources.json`, so any agent can re-fetch the exact material. The paper PDF was supplied by the owner (sha256 in the manifest); keep the original. Third-party content is not committed because the arXiv paper's license was not verified and the artifact repo has no license file.

## Verified facts (read at the pins in the manifest)

### From arXiv 2609.33401 (full text)

See `docs/JEV_COMPARABILITY.md` section 7 for findings. Protocol summary: partitions development / selection / confirmation / test; Jev 1.13 via hosted API; Laya pinned English checkpoint on CPU float32; Decider about 2B on MPS float16; Nimble about 9B on MLX; unsafe probability read as P(B)/(P(A)+P(B)) for generative judges at the answer token; temperature fitted on development data in [0.05, 20] by minimizing NLL; ECE with ten equal-width bins; 2,200 held-out test inputs (WAInjectBench 1,612, R-Judge 236, AgentHarm 352).

### How the study called hosted Jev (from its artifact code, `yxsec/system-one-security-eval` @ `78910f0`)

- Jev was reached through **OpenRouter's decisions endpoint** (`https://openrouter.ai/api/alpha/decisions`), model id **`typesafe/jev-1.13`**, bearer-token auth. This **differs** from the `api.typesafe.ai/v1/systemone` endpoint circulated earlier, which remains unverified.
- Request body: `model`, `state` (the input text) and `questions` (a map from question id to a typed question). Response: `answers[question id]` with `choice`, `probabilities` keyed by option label, and a separate `confidence` value; plus `usage`, response `id`, returned `model` and `provider`.
- Good practice we should copy in our adapter (idea, not code): read the probability by option label, never by position or from the separate confidence value; validate that probabilities are finite, in [0,1] and sum to about 1; record returned model, provider, response id, latency and cost per call; classify transport errors, HTTP errors and invalid output separately from wrong answers; ask one question per request.
- The artifact redacts credentials from recorded requests and responses and runs without retry loops in its core runner.

### Local model pins used by that study (useful for our Q3/Q8 provenance)

| Candidate | Source repo | Revision |
| --- | --- | --- |
| Laya (English) | `convaiinnovations/laya` | `5e7b2b1b8ca2ecdd3f2322d94069c9b6ce7e844b` |
| Decider (about 2B) | `Mapika/decider-2b` | `fa996cea58e1c1d8d1ab4d7124154f303b017f95` |
| Nimble (about 9B) | `bespokelabs/Bespoke-Nimble-9B` | `e93fabce8fcee46e7e8b45e2d955b8a4f0035917` (base `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a`) |

These are what that study ran, not a decision about what we run. Confirm each on the Mac before use.

### Benchmark sources that study used, with their license cautions

R-Judge, WAInjectBench (no general redistribution grant at the pinned trees) and AgentHarm (MIT plus an AI-safety-use restriction). The artifact does not mirror their text. We do not use them.

### From the InfoQ release article (pasted by the owner 2026-10-05; secondary, original page not opened)

Recorded in our own words. Each item is **reported**, not verified against TypeSafe's documentation.

- **Interface:** a caller sends a state (string or structured data) plus typed questions; Jev answers all questions in one parallel pass with Choice, Score and Noul results, each with a probability distribution and a confidence value, so code can act above a threshold and escalate below it.
- **Vendor figures:** input priced at USD 0.042 per million tokens, output free; 32,000-token context window; end-to-end latency quoted at 70-500 ms; trained with a method TypeSafe calls Reinforcement Learning for Calibrated Decisions.
- **Independent measurements cited by the article:** a safety classifier 5-18x faster than the LLM it replaced (Vercel engineer); an email-classification test where Gemini was slightly more accurate but 10-20x more expensive, with Jev valued for returning a real probability; an analysis of 12,759 launch posts putting user-reported speedups at a median of 7x against a 193.6x headline, cost savings at a median of 30x, and latency at a median of 76 ms (upper quartile 270 ms). This agrees in direction with the `jev-aita` author's finding that the headline speed multiples were not reproduced.
- **Documented weaknesses (the "jev-1.13 jaggedness" page):** unreliable counting, arithmetic and date comparison, and accuracy loss on large noisy state; keep maths in code. This corroborates our planned date, counting and long-input controls.
- **Version pinning advice:** pin an explicit version such as `jev-1.13.0`, not the moving `jev-latest` or `jev-preview` aliases. `jev-ood-calibration` independently saw `jev-latest` fail on one gateway.
- **A vendor "System One adapter"** is said to run existing models against the same schema when benchmarking. This could help comparability, but we have not seen its documentation; find and read it before relying on it.
- **Developer comment worth keeping:** Jev cannot return an invalid type but can return a wrong valid value. Our harness already counts schema failures and wrong answers separately.
- **Context:** TypeSafe AI is described as a San Francisco lab founded by Diogo Almeida, Erik Gafni and Sasha Sheng. Hosted by Vercel AI Gateway, Netlify and a LangChain integration, per the article.

### From arXiv 2609.37647, the 37-dataset evaluation (read; owner-supplied PDF, plus its code repository)

**The most rigorous Jev source so far:** three authors from the University of Bonn, the Lamarr Institute and Fraunhofer IAIS; pinned `jev-1.13.0`; full evaluation splits; one template per dataset frozen after a 20-example pilot on a training or validation split; no prompt tuning on evaluation data; 95% bootstrap intervals; code (MIT) and all raw responses released. Still a preprint.

- **Request shape (vendor interface as used):** a `state` (string or JSON object/array) and a map of named questions. Choice: up to 255 options, returns the chosen option, a probability per option and a confidence value. Score: 2 to 10 described levels, returns per-level probabilities, a probability-weighted score and confidence. Noul: probability of yes. Questions share the state but are answered independently. Instructions can refer to state fields by name in backticks. Limit: 32k tokens for the state plus the longest question. Price USD 0.042 per million input tokens, output free. The harness calls the API through the official `typesafe_sdk` client.
- **Scale and cost:** 346,009 requests, 217.9 million input tokens (630 per request on average), USD 9.15. **Mean client-side latency 0.36 s per request at 32 concurrent requests, including network time** (latency by category 0.35-0.37 s). One over-long request was rejected; all others answered.
- **Accuracy:** strong on short, gist-level decisions in widely spoken languages (for example IMDB 96.5%, SST-2 96.4%, ARC 98.8%, HellaSwag 95.5%, language ID 99.6%); routing CLINC150 89.5% (151 options) and Banking77 79.7% (77 options); weak on noisy or fine-grained labels (Emotion 58.5%, SST-5 57.9%), low-resource languages (AfriXNLI 64.0%), legal judgment (AGB-DE F1 0.204) and rubric scoring of generated text (HelpSteer2 Spearman 0.412). Beat Qwen3.8-27B on 27 of 37 datasets (none of Qwen's 9 leads outside the intervals) and Gemma-4-E4B on all 37.
- **Calibration:** Choice probabilities well calibrated (pooled ECE 0.028 over 279,925 answers; per-dataset mean 0.061; overconfident where wrong). Single Noul slightly under-confident (ECE 0.052), so positives often fall below 0.5. Multi-label Noul (many questions in one request) strongly over-predicts yes (mean P(yes) 0.209 vs observed 0.041). **A fixed 0.5 threshold is often a poor operating point**: prompt-injection detection had perfect precision but 50% recall at 0.5 despite AUROC 0.982; thresholds tuned on 1,000 training examples raised UNFAIR-ToS micro-F1 from 0.499 to 0.748. Confidence supports selective prediction (Banking77 79.7% to 96.3% at 50% coverage).
- **Weak spots and contamination caution:** consistent with the vendor's jaggedness page (arithmetic, long inputs). Jev scored unexpectedly well on calculation-heavy MMLU subjects (94.3%), unlike the open models; option rotation left this unchanged and withholding the question dropped it to near chance, which rules out shallow memorization but not memorized question-answer pairs. The authors treat results on long-established English benchmarks with caution.
- **How they made other models comparable (useful method):** each open-weight model sees exactly the same request, rendered as a prompt where every answer option is one token; a single forward pass gives the exact next-token probabilities over the option codes, renormalised, with no text generation and thinking disabled. A Jev-style confidence is computed as (K*pmax - 1)/(K - 1) for K options. Their code provides this backend.
- **Stated limitations:** one template per dataset; prompts written for Jev, not tuned for the open models; each request run once (no run-to-run variance); latency measured client-side with network time; results refer to `jev-1.13.0` only.
- **License caution on the released responses:** the Jev responses on Zenodo are under a "Jev Responses License 1.0" that allows research, evaluation and benchmarking but **prohibits using them to develop a product similar to or competing with TypeSafe's**, and requires the license to travel with derived data. We have not downloaded or used them. Whether this project or the proposed triage gateway could count as "competing" is an owner/legal question; avoid using those responses until it is answered.
- **Vendor URLs cited:** `https://docs.typesafe.ai/model-jaggedness/jev-1.13` and `https://docs.typesafe.ai/models` (not opened).

### From arXiv 2609.28940 (pentest harness; read in part, owner-supplied PDF)

A single independent author's preprint. Its case study ran each condition **once** on one target, changed the harness between the first run and a re-test, and says itself that it is not a controlled experiment. Treat it as design ideas, not evidence.

- **Reported specifications table** (its own caution: measured on different tasks and hardware, so rows are not comparable): Jev p50 latency 236-276 ms for one question, USD 0.042 per million input tokens, context window "not published", cloud API only; Laya built on ModernBERT-large (421M parameters), Apache 2.0, 32.8-39.5 ms on a T4 GPU, context **512 tokens (English) or 1,024 (multilingual)**, self-hosted, supports fine-tuning. Quoted accuracy figures: AG News Jev 0.910 vs Laya 0.950; Banking77 (77 labels) Jev 0.870 vs Laya 0.425; typed-decision set Jev 0.727 vs a fine-tuned Laya 0.766; ECE Jev 0.246 vs Laya 0.081 after temperature scaling. These conflict in size and sign with other circulated ECE figures; none is verified.
- **Design lessons worth keeping:** questions in one request are evaluated independently by design; the model layer should be additive, with deterministic checks keeping priority; failure is asymmetric (false negatives can make the layer worse than none, so monitor disagreements with the baseline); named failure modes: evidence-format mismatch, domain vocabulary, adversarial evidence, calibration drift, threshold sensitivity; context limits need explicit ablations.
- **Relevance to us:** a 512-token cap means some of our cases, with their context blocks, may be too long for the English Laya checkpoint. The runner must mark such inputs unsupported, not truncate them. Jev being cloud-only conflicts with local-only operation; Laya can run locally.

### From arXiv 2610.01079 (Jev-IDS; read in part, owner-supplied PDF)

Preprint by three authors (UNIPAMPA). Uses NSL-KDD, an old benchmark the authors call historical, with 2,000 test flows in five coarse categories, three sampling seeds, and k labelled examples per category.

- **Findings reported:** the comparison LLM (named Gemini 3.6 Flash in the body) had higher F1 than Jev at every k (for example 0.880 vs 0.856 at k=1; exact McNemar p < 0.001), mainly through higher recall; Jev's request latency was about 0.31-0.34 s against 1.99-2.65 s (5.9-8.6x) and its estimated list-price cost 10-25x lower; once labelled examples were supplied, Jev's recall on withheld attack types was higher (0.747 vs 0.713 at k=1), but the authors warn against calling that general superiority and note it concerns withheld attack types within one benchmark. A few-shot Random Forest reached recall 1.0 at k=1 with precision 0.598. Probability calibration was **not** evaluated, and a common threshold was used for every detector.
- **Reliability flags:** the abstract names a different comparison model (GPT-5.6 Luna) and a 300-flow pilot with 5,400 decisions (F1 0.859), while the body reports Gemini 3.6 Flash and 2,000 flows (F1 0.856 at k=1). We could not reconcile them. Their artifact repository (`github.com/jev-ids/jev-ids`) is named but unread.
- **Convention we do not copy:** the paper treats calls with no valid output as benign (fail-open) when computing metrics. Our scorecard treats a non-answer as a miss in the strict forms of must-page recall and spoof-escalation-kept.
- **Relevance to us:** same shape of trade-off we want to measure (accuracy against latency and cost), a few-shot label-budget arm that matches our planned S7 label-budget subsets, and a reminder that recall and false-alarm load must be read together.

### From the other GitHub sources (read at the pins in the manifest; all MIT unless noted)

- **`scienthoon/jev-ood-calibration`** (independent, 2026-09-19, about USD 0.06 of calls): Jev reached through the Vercel AI Gateway as model id `typesafe-ai/jev` (the `typesafe-ai/jev-latest` id from the AI SDK docs returned "Model not found" there). On three public benchmarks accuracy was 86-94% with small calibration error (ECE 0.024-0.032), but those sets are probably in Jev's training data. On 900 rule-generated support tickets: queue choice 89.0%, "customer angry" 91.7%, and an organisation-specific priority rule only 44.7% with mean stated probability 0.74 (ECE 0.325, 4.4x its noise floor for the pooled set). The author later corrected the temperature-fit figures: Jev's probabilities are quantised to 0.01 and often use exact 0 or 1, so the result depends on how exact zeros are floored in log-loss. **Lesson for us:** a model can be fluent and well calibrated on familiar tasks and confidently wrong on a rule it cannot know; our held-out wrapper families and B' cases target the same risk. Record how exact 0/1 probabilities are floored in NLL.
- **`jyatesdotdev/jev-logtriage`** (independent, not an official TypeSafe project): the same use case as ours. Collapses repeated log lines, asks Jev six questions in one call, and maps the answers in code to suppress / watch / review / notify / page; low confidence never acts automatically. Vendor docs URLs it links: `https://docs.typesafe.ai/introduction/quickstart`, `https://docs.typesafe.ai/introduction`, API keys at `https://console.typesafe.ai/settings/keys` (none opened).
- **`fstandhartinger/jevbench`** (Benchmark Heaven's benchmark, not affiliated with TypeSafe): the upstream of the `f8ce713` commit pinned by Open-Jev, which exists. Its README ranks Jev 1.13.0 fourth of 91 ranked systems with a blended JevBench Score of 63.29, in a leaderboard led by small open models (Imajev-4B 67.37). That score blends several axes and is **not** an accuracy percentage; do not compare it with our metrics.

## How to verify each source later

1. GitHub repos: use the recipe in `jev_sources.json` (`verification_recipe.github`). Compare the commit, confirm the license file, and re-read the passages cited above.
2. The arXiv PDF: compare its sha256 with the manifest, then confirm the title and arXiv id on page 1.
3. Vendor pages and the 37-dataset paper: not read yet. When read, record the date, page title and any model version string in the manifest, and replace "NOT read" with the pin or hash.
4. Anything changed upstream after the pinned commit is not evidence for the pinned claim; re-pin and re-read before updating a figure.

## Not read (still open)

(The InfoQ article was read from owner-pasted text only.)

the vendor announcement and docs (including the jaggedness and models pages), the Zenodo responses (blocked here), the full `jev-aita` study and the rest of the READMEs and code of the three repositories above, the LiteLLM benchmark. Close these by owner-supplied PDFs/pastes, a widened network allowlist (`arxiv.org`, `typesafe.ai`), or the Mac agent.
