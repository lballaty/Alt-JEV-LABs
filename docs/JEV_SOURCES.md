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

arXiv 2609.37647 (37 datasets), the vendor announcement and docs (blocked here), the full `jev-aita` study and the rest of the READMEs and code of the three repositories above, the LiteLLM benchmark. Close these by owner-supplied PDFs/pastes, a widened network allowlist (`arxiv.org`, `typesafe.ai`), or the Mac agent.
