# llamaCPPManager changes to support the benchmark (proposal)

Status: **Draft / proposed.** Based on reading `arionrepo/llamacppmanager` at `b7d27f9` (VERSION `2026.09.10.2`) on Linux. Nothing was run on the M4. Items marked *verify* depend on macOS or llama.cpp behavior that must be confirmed on the Mac. Implementation happens in the manager repo; this file is the requirements hand-off. Finalize it after the model inventory on the Mac (Q1–Q3).

## Principles

1. **Headless first.** Every capability is a CLI/JSON (and MCP) feature before it is a UI feature. Benchmark runs are scripted and must not depend on the GUI.
2. **The manager provisions and reports; the benchmark measures.** The benchmark never starts, stops or downloads models (D10). So the manager has to expose readiness, provenance and resource data in a stable, versioned format.
3. **Harness-side fallback.** If a manager change is not done, the harness implements the fallback noted below, so the benchmark is never blocked.

## What exists today (from source)

| Capability | Today | Gap for testing |
| --- | --- | --- |
| `status --json` | Per model: up, port, pid, model_path, filename, quantization, size, deployment_type, mode, `ram_mb`, health | No schema version. `version` is a heuristic (`"llama.cpp"` string from `/health`), not the build number. No file hash, no MLX snapshot revision, no effective launch args |
| Memory | `ram_mb` = process **RSS** via psutil | On Apple Silicon, Metal/unified-memory allocations for weights and KV cache may not be fully counted in RSS (*verify*). This matters for the 80 GB gate (D11) |
| Readiness | Health probe (`/health`, `/v1/models`, `/`) | No `start --wait` that returns only when the model is loaded and serving, with a timeout and exit code |
| Exclusivity | Exclusive model groups | No way to mark a model "under test" to block stop/restart/other starts (GUI, monitor auto-restart) during a timed run |
| Offline | MLX runs `mlx_lm.server --model <HF repo id>` | No offline switch. A cache miss can download during a run |
| MLX memory | Sets `MLX_METAL_MEMORY_LIMIT` / cache limit | Limit not reported in status |
| Query helpers / MCP | `query_completion`, `query_chat`, `model_status`, start/stop, list | Default `temperature=0.7`. No manifest or ensure-ready tool |
| Lifecycle log | `lifecycle.jsonl` with versioned event schema | No benchmark run correlation, so a crash or restart during a run can't be tied to that run |

## Proposed changes — API / CLI

| # | Change | Why (benchmark need) | Priority | Harness fallback if not done |
| --- | --- | --- | --- | --- |
| M1 | `llamacpp-manager manifest --json` with `schema_version`: one record per model with name, runtime, endpoint, model_path, **file sha256** (cached by path+size+mtime), quantization, **llama.cpp build number + commit** (from `llama-server --version`), **MLX HF snapshot revision**, effective argv (ctx, n_gpu_layers, batch, threads, flash-attn, template/jinja), env subset (offline flags, MLX limits) | Provenance required by AGENTS.md rule 7; the preflight contract (WS8) | **Must** | Harness hashes files, runs `--version`, reads HF cache; slower and duplicated |
| M2 | Optional `local_artifacts` section in the manager config/manifest for **non-served** models (Laya, ModernBERT heads, GLiClass, Von, SemIf checkpoints): path, revision, sha256, license | Keeps *all* model inventory in one place, matching D10; answers Q3 cleanly | **Must** (or decide harness-owned `configs/local_models.yaml`) | Harness-side manifest |
| M3 | `start <model> --wait --timeout S` → exit 0 when serving (health OK and a 1-token probe succeeds), non-zero with a reason otherwise; `ensure <model> --exclusive` stops other members first | Deterministic setup between candidates; no timing a half-loaded model | **Must** | Harness polls `/health`, but the harness must not start models (D10), so this is effectively manual |
| M4 | Memory: report **physical footprint** per process (macOS `phys_footprint` / `footprint`-equivalent) alongside RSS, plus system unified-memory pressure. Add `monitor sample --model X --interval 0.5 --out file.jsonl` for peak-during-window | The 80 GB gate needs a correct peak that includes GPU/unified allocations (*verify* the RSS gap) | **Must** | Harness samples the pid itself (needs the same macOS API) |
| M5 | Offline: per-model or global `offline: true` → sets `HF_HUB_OFFLINE=1` (and equivalents), and refuses to start if the snapshot is missing | No downloads during runs (AGENTS.md rule 4, D10) | **Must** | Set `env: {HF_HUB_OFFLINE: "1"}` by hand in config (Q2) |
| M6 | Test lock: `lock <model> --reason benchmark --ttl 2h` / `unlock`. While locked: monitor auto-restart paused, GUI/CLI stop/restart/start of *other* models refused unless `--force`, all logged | A restart or a second model loading mid-run invalidates timing and memory | **Must** | Operator discipline only |
| M7 | Lifecycle correlation: `lifecycle mark --run-id R --event benchmark.run.begin/end` (or accept events from the harness), and include crash/restart events in `manifest`/`status` since a timestamp | Tie backend failures to a run; report exceptions vs wrong answers correctly (AGENTS.md rule 8) | Should | Harness reads `lifecycle.jsonl` by time window |
| M8 | System snapshot: `system --json` → chip, unified memory total, macOS version, power source/mode, thermal pressure | Timing provenance (blueprint: power mode, hardware) | Should | Harness runs `sysctl`/`pmset` itself |
| M11 | **Co-tenancy report** in `system --json`: memory used by everything the manager knows about (other models, Colima/Docker VMs, MyRAGDB) plus total used, pressure and swap. Include the Metal GPU working-set limit (`recommendedMaxWorkingSetSize`; the `iogpu.wired_limit_mb` sysctl if set; *verify* values on the M4 Max) | The 128 GB machine is shared; the effective memory gate (D12) depends on the measured baseline. A model larger than the GPU working-set limit may fail or spill regardless of free RAM | **Must** | Harness reads `vm_stat`/`memory_pressure`/`sysctl` itself; cannot attribute memory to manager-owned VMs as cleanly |
| M9 | Query/MCP passthrough: explicit `temperature`, `seed`, `top_k`, `n_probs`/logprobs, `json_schema`/`grammar` on chat and completion; scripted callers must pass temperature (no hidden 0.7 default) | Useful for agents and manual checks; the benchmark calls endpoints directly anyway | Could | Harness calls the server API directly |
| M10 | MCP tools: `model_manifest`, `ensure_model`, `lock_model`, `system_info` | Lets an agent orchestrate test setup through the same contract | Could | CLI |

## Proposed changes — UI (macOS menu bar app)

| # | Change | Why | Priority |
| --- | --- | --- | --- |
| U1 | **Test-lock indicator**: banner and per-model lock icon; start/stop disabled for locked or conflicting models, with the reason shown | Stops an accidental click from invalidating a run | Should (with M6) |
| U2 | **Memory panel**: per-model physical footprint and peak, stacked against a configurable budget bar (default 80 GB) | See at a glance whether a candidate fits the gate | Should (with M4) |
| U3 | **Provenance card** per model: build, sha256, quantization, revision, launch args, offline flag; "Copy as JSON" | Fast manual verification before a run | Could (with M1) |
| U4 | **Offline badge / download warning** for MLX entries whose snapshot is missing | Prevents surprise downloads | Could (with M5) |
| U5 | **Candidate set view**: pick a group, "run exclusively", show readiness state | Convenience for manual comparison sessions | Could |

## Suggested order

1. Inventory on the Mac (Q1–Q3): which models, runtimes and sizes.
2. **M1 + M5 + M3** (provenance, offline, readiness) → enough for the WS8 preflight.
3. **M4 + M11** after verifying the RSS vs physical-footprint gap on a real model; these gate the memory budget (D12).
4. **M6 + U1** before the first timed pilot run.
5. The rest as needed.

## Assumptions

- The manager stays the single owner of model lifecycle on the M4 (D10); the benchmark only reads.
- Manager changes follow that repo's own conventions (CHANGELOG, VERSION, tests, GUI slice tests).

## Review flags

- M2: should non-served checkpoints live in the manager (single inventory) or in this repo (`configs/local_models.yaml`)?
- M4: confirm on the M4 that RSS understates Metal/unified allocations for llama.cpp and MLX before building on it.
- Implementing in the manager repo needs push access for that session (`arionrepo/llamacppmanager` is read-only here).
