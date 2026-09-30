# Integration with llamaCPPManager (model boundary)

Status: **Draft / proposed — not implemented, not tested on the M4.** Source reviewed: https://github.com/arionrepo/llamacppmanager at commit `b7d27f9` (VERSION `2026.09.10.2`), read on a Linux host. Nothing below was executed against a running manager.

## What the manager provides (verified from source)

| Aspect | Finding | Source |
| --- | --- | --- |
| Runtimes | `native` (llama.cpp `llama-server`, GGUF), `container` (llama-server in Docker), `mlx` (`python -m mlx_lm.server`), `mlx-vlm` (`python -m mlx_vlm.server`) | README "Supported Backends" |
| API | All runtimes expose OpenAI-compatible `/v1/chat/completions` on `host:port` per model | README |
| Config | `~/Library/Application Support/llamaCPPManager/config.yaml` (override: `LLAMACPP_MANAGER_CONFIG_DIR`). Per model: `name, model_path, host, port, deployment_type, mode, ctx_size, n_gpu_layers, group, metadata, args, env` | `config.py` `ModelSpec`, `utils.config_path` |
| Status | `llamacpp-manager status --json` → per model: `up, pid, host, port, version, model_path, model_filename, file_size_gb, quantization, deployment_type, mode, ram_mb, cpu_percent, health_state, process_source` | `cli.py` `_gather_status` |
| llama.cpp build | Canonical local build with a version floor of **b10154**; the build is recorded per the manager's policy | `docs/LLAMA-CPP-VERSION-POLICY.md` |
| MLX models | `model_path` is a Hugging Face repo ID passed to `mlx_lm.server --model` | `mlx_process.py` |
| Memory control | Exclusive model groups (only one member running at a time) | `config.py` groups |
| Audit | Lifecycle events in `~/Library/Logs/llamaCPPManager/lifecycle.jsonl` | README |

## What this means for the benchmark

1. **The manager covers generative arms only.** It serves chat-completion servers. The encoder/classifier candidates (Laya-MLX, ModernBERT MPS heads, GLiClass, Von, SemIf's logit path) are Python libraries loaded in-process, not servers, so the manager does not provision them. These need their own read-only local-path manifest, listing path, revision and sha256 for each. Proposed: `configs/local_models.yaml`, filled by hand or by a script on the Mac, never downloaded by the benchmark.
2. **New generative adapter: `generative_managed`.** It calls the manager-served endpoint (`http://127.0.0.1:<port>/v1/chat/completions`) instead of loading weights in-process with `mlx_lm.load` as `models/generative_mlx.py` does today. This matches how the model would actually be deployed, and it keeps the benchmark from ever loading or downloading weights. The existing in-process adapter stays as a separate arm, labeled as such.
3. **Preflight reads `status --json`, not the YAML.** Before a run, for each requested generative model:
   - require `up: true` and `health_state` healthy, and the port matches config
   - record in raw results: `version` (llama.cpp build), `model_filename`, `quantization`, `file_size_gb`, `deployment_type`, `mode`, `ctx_size`
   - compute the sha256 of the GGUF at `model_path`, read-only (the manager does not record a hash)
   - if something is not up or not healthy, mark it `unavailable` with the reason; don't start it
4. **Request parameters are set by the benchmark, never inherited.** The manager's own `query` helper defaults to `temperature=0.7`. The benchmark must send `temperature=0`, a fixed `seed`, `max_tokens`, and the exact prompt/template, and record all of them.
5. **Constrained decoding becomes testable.** llama.cpp's server documents grammar/JSON-schema constrained sampling and token log-probabilities. Through the manager's native runtime, that gives:
   - a genuine **grammar-constrained** arm, which the harness currently lacks (it has prompt-only and finite-candidate JSON)
   - a log-probability-based Noul probability instead of a generated decimal

   **To verify on the M4:** the exact request fields accepted by build ≥ b10154, and whether `mlx_lm.server` supports any equivalent (assume not until tested).
6. **Offline guarantee for MLX runtimes.** `mlx_lm.server --model <HF repo id>` resolves through the Hugging Face cache and can download on a cache miss. For benchmark runs, the manager config for those models should set `env: {HF_HUB_OFFLINE: "1"}`. The preflight records the resolved snapshot revision from the local HF cache. This is a change to the manager config on the Mac, not to this repo.
7. **Timing semantics.** Latency for `generative_managed` includes local HTTP and JSON (de)serialization. Report it as the served-deployment path, separately from in-process timings. Run one model at a time: use an exclusive group, or check that `status --json` shows no other model `up`, and record co-running models and `ram_mb` in provenance.

## Proposed work (new WS8)

| Step | Files | Needs the Mac |
| --- | --- | --- |
| Preflight: parse `status --json` (or a saved snapshot), check health, hash GGUF, emit provenance block | `evaluation/preflight.py`, tests with recorded JSON fixtures | Final check only |
| `generative_managed` adapter: prompt-JSON, grammar/JSON-schema, and logprob Noul modes; backend errors kept separate from schema failures | `models/generative_managed.py`, tests with a local stub HTTP server | Yes, to verify fields on b10154 |
| `configs/local_models.yaml` schema + loader for in-process encoder candidates | `configs/`, `models/` | Paths/hashes filled on the Mac |

## Assumptions

- The benchmark runs on the same M4 as the manager, against `127.0.0.1` only (AGENTS.md rule 4).
- The manager is not modified by this repository. Any needed manager change (offline env, groups) is listed here for the owner to apply.

## Review flags

- Which manager model names and ports are the intended generative candidates?
- Confirm that setting `HF_HUB_OFFLINE=1` on the MLX entries is acceptable for everyday use, or use a benchmark-only group/profile instead.
