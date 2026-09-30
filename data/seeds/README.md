# Seed registry provenance (WS1)

This directory holds the **seed registry**: de-identified log *templates* and
security *command-line* seeds, pinned to exact upstream commits, that later
workstreams (WS2 rubric, WS3 cohort generator) fill and label. It is produced by
`data/seed_registry.py` (workstream WS1 of `docs/DATASET_PLAN_V2.md`).

Nothing here is a benchmark result or a label. These are inputs to a synthetic
fixture, and — per `AGENTS.md` — they are labelled as generated/synthetic
wherever they are used, never mixed with real measured data.

## Files

| File | What it is |
| --- | --- |
| `registry.jsonl` | One JSON record per seed template (newline-delimited). |
| `registry.manifest.json` | Build summary: upstream commits, per-source counts, source-file sha256s, licenses. |

## Sources and pinned commits

| Source | Commit | License / terms | What we copy |
| --- | --- | --- | --- |
| [`logpai/loghub`](https://github.com/logpai/loghub) | `dd61d0952749ee7963bde24220d1be5ede023033` | Research/academic use; any use or distribution must reference the repo URL and cite the Loghub paper (Zhu et al., ISSRE 2023). | **Only** the `*_2k.log_templates.csv` files for OpenSSH, OpenStack, BGL, HDFS, Linux — the parsed event templates with `<*>` placeholders. |
| [`redcanaryco/atomic-red-team`](https://github.com/redcanaryco/atomic-red-team) | `388942adbd9641f4dfdcf079d7efe9a75ec0ac43` | MIT. | A small, explicitly enumerated set of Linux test command lines mapped to ATT&CK technique IDs. |

### What is deliberately **not** copied

Loghub also ships raw `*.log` and `*_structured.csv` files. Those contain real
public IP addresses and usernames (e.g. the OpenSSH auth logs). `AGENTS.md`
rule 4 forbids committing identifiable traces, so the extractor reads **only**
the `*_templates.csv` files and never opens the raw or structured files. A test
(`tests/test_seed_registry.py::test_extract_loghub_reads_templates_only_and_no_raw_leak`)
builds a fixture with decoy raw files and asserts their sentinel IP/username
never reach a record.

Loghub's event *labels* are anomaly/normal (and only for some systems); they are
**not** route/score/noul labels. This registry carries no such labels — the
label-set decision (`service_outage` vs the five v2 routes) is open and owned by
WS2/WS3.

## Record schema (`registry.jsonl`)

Every record has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | string | `"loghub"` or `"atomic-red-team"`. |
| `system` | string | Loghub system (`OpenSSH`, `OpenStack`, `BGL`, `HDFS`, `Linux`) or `"linux"` for ATT&CK seeds. |
| `template_id` | string | Stable id: `"<System>-<EventId>"` (Loghub) or `"<Technique>-<guid8>"` (ART). |
| `template` | string | The template text (with `<*>`) or the command line (with `#{arg}` tokens). |
| `upstream_commit` | string | The pinned source commit. |
| `source_file` | string | Path of the source file within the upstream repo. |
| `source_file_sha256` | string | sha256 of that source file's bytes. |
| `license` | string | The license/terms string for the source. |

Loghub records additionally carry:

| Field | Type | Meaning |
| --- | --- | --- |
| `num_placeholders` | int | Number of `<*>` placeholders in the template. |
| `placeholder_kinds` | list[string] | The kind inferred for each placeholder, in order (see below). |

Atomic Red Team records additionally carry `attack_technique`, `attack_test_name`,
`attack_guid`, `executor`, and `input_arguments` (declared argument defaults).

## Synthetic entity filler (`data/entity_filler.py`)

Templates are turned into runnable synthetic evidence by a **deterministic,
seeded** filler that replaces each `<*>` based on its inferred kind:

- **Determinism:** the output of `fill_template(template, template_id, seed)` is
  fully determined by those three inputs (no clock, no global RNG), so any fill
  can be regenerated and its provenance recorded (`AGENTS.md` rule 7).
- **IP safety:** every value classified as an IP is drawn from the RFC 5737
  documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`),
  which are never routable. Dotted version/decimal runs are generated so they can
  never coincidentally read as a routable dotted quad. A test fills every sample
  template across 100 seeds and asserts no non-RFC 5737 IP is ever emitted.

Inferred placeholder kinds are heuristic and logged at build time. Current kinds:
`ip`, `port`, `username`, `uid`, `hostname`, `block_id`, `path`, `version`,
`number`. The classifier is context-based (it reads the literal text around each
`<*>`), so it is approximate; `placeholder_kinds` records exactly what was
assumed for each template.

## Regenerating

Requires network access to clone the pinned commits:

```bash
uv run python -m data.seed_registry --out data/seeds \
    --loghub-rev dd61d0952749ee7963bde24220d1be5ede023033
```

To rebuild offline from existing checkouts (no network), pass
`--loghub-path <dir>` and `--art-path <dir>`. A failed network fetch raises a
clear error; there is no silent fallback to stale data.

## Verification status

Verified on this Linux host (2026-09-30):

- Both sources cloned at the pinned commits above; template counts match
  `docs/DATASET_PLAN_V2.md` (OpenSSH 27, OpenStack 43, BGL 120, HDFS 14,
  Linux 118 = 322 Loghub templates) plus 8 Atomic Red Team seeds = 330 records.
- No committed template contains a routable IPv4 address, equals any raw
  `*.log` / `*_structured.csv` line, or diverges from its source
  `*_templates.csv` value.
- `uv run pytest -q` passes (13 tests).

Not verified here (no such step in WS1): any model behaviour, benchmark number,
or Apple-Silicon result.
