# Reference-only seed sources

Status: **implemented and tested on Linux with invented fixtures; one real fetch, verify and build was run on this host on 2026-10-04.** Nothing here is a benchmark result. Decision D28 (see `docs/TRACKER.md`): any seed source whose license does not clearly allow us to publish its content is **not committed**. We publish only a reference. You fetch the files yourself and derive a local registry that stays on your machine.

Sources that were already committed (Loghub templates, Atomic Red Team) are unchanged: `data/seeds/registry.jsonl` and its manifest are not touched by anything below.

## What is published and what is not

| Published in this repo | Never published |
| --- | --- |
| `data/seeds/references.json`: where to get each file, the pinned commit, expected sha256, license, format, extractor name | The fetched upstream files |
| `data/seed_references.py` (fetch, verify, build tool) | `data/seeds_local/references_registry.jsonl` and its manifest (derived templates) |
| This guide | Any cohort dataset generated from that registry |

`data/seeds_local/` and `.seed_refs_work/` are git-ignored. The tool refuses to write fetched or derived files anywhere git would track them.

## The references

Pinned commits are full 40-character shas. Licenses were read from each repository's root `LICENSE` at that commit (2026-10-04). This is not legal advice.

| Id | Repo | Commit | License | What we point at | Yield on the first real run |
| --- | --- | --- | --- | --- | --- |
| `logstash-patterns-core` | `logstash-plugins/logstash-patterns-core` | `74a4098582d3331a2b9b18c04d2446f2c0efb648` | Apache-2.0 | `spec/patterns/syslog_spec.rb`, `spec/patterns/firewalls_spec.rb` (Ruby tests holding syslog, PAM, Cisco-style and Linux firewall lines) | 27 templates |
| `vector` | `vectordotdev/vector` | `9aee1f50eefe4c077ba9d640edd7cbbe3b7dc1a2` | MPL-2.0 | `src/sources/syslog.rs` (Rust tests with syslog lines) | 3 templates (small) |
| `wazuh` | `wazuh/wazuh` | `74ed87cb8775ab2dcfb74835ca9ab91f87cac0be` | GPL-2.0 with OpenSSL exception | `tools/manager_benchmark/sample_payloads/engine/syslog.log` (plain syslog, many repeated lines) | 10 templates |

Not listed as sources, on purpose: SecRepo, OpenEnv SRE triage, MITRE ATT&CK and Zenodo Loghub full logs are marked `status: unverified, excluded` in `references.json` with no fetch instructions (`docs/SEED_SOURCE_LICENSES.md`).

Gaps you should know about, found by looking at the pinned trees:

* The Wazuh commit above no longer contains `ruleset/decoders` or `ruleset/rules` XML (the ruleset directory holds only SCA, MITRE and a README). The only usable sample lines there are in the benchmark payload.
* Vector has few real log samples in tests. Its VRL function docs are no longer in this repository at this commit. Its yield is small and mostly structured-data shapes.
* No PAM-specific fixture file exists in Logstash at this commit; PAM lines appear only inside the syslog spec.

## What the license means for you

* **Apache-2.0 (Logstash).** Permissive. Redistribution would be allowed with the license text and notices kept. We still keep the derived text local-only for consistency under D28.
* **MPL-2.0 (Vector).** File-level copyleft: if you copy or modify an MPL file, that file stays under MPL and its source must be available. We never copy the files; we only point at them. Do not paste Vector test strings into any file you publish.
* **GPL-2.0 (Wazuh).** Strong copyleft. Copying GPL content into a project can pull the combined work under the GPL. We copy nothing and publish nothing derived from it. Do not paste Wazuh lines or derived templates into anything you publish.

## Commands

Run from the repository root. All three need the project environment (`uv sync`).

```bash
# 1. Fetch the pinned files (network; sparse, shallow, by commit sha).
uv run python -m data.seed_references fetch  --refs data/seeds/references.json --workdir data/seeds_local/fetched

# 2. Check sha256 of every listed file and each license file. Fails on any mismatch or missing file.
uv run python -m data.seed_references verify --refs data/seeds/references.json --workdir data/seeds_local/fetched

# 3. Derive templates. Verifies first, then writes data/seeds_local/references_registry.jsonl (+ .manifest.json).
uv run python -m data.seed_references build  --refs data/seeds/references.json --workdir data/seeds_local/fetched
```

`--only <id>` limits a command to one source (repeatable). `--out <path>` changes the build output, which must also be git-ignored.

### What `build` produces

One JSON line per template with the same fields as `data/seeds/registry.jsonl` (`source`, `system`, `template_id`, `template`, `upstream_commit`, `source_file`, `source_file_sha256`, `license`, `num_placeholders`, `placeholder_kinds`, and the empty Atomic Red Team fields) plus `redistribution: "local-only"`. The manifest next to it holds counts per file (candidates, kept, skipped, duplicates), the registry hash and `contains_local_only_seed_text: true`. It holds no seed text.

The extractors:

| Extractor | File format | Handles |
| --- | --- | --- |
| `syslog_lines` | Text, one syslog line per line | Traditional (RFC 3164) and RFC 5424 headers, vendor message ids such as `%ASA-4-...`. Header (priority, timestamp, host, pid) is dropped, as Loghub's templates do; the program name goes into `template_id`. |
| `ruby_spec_literals` | Ruby test files | Quoted string literals that start like a log line. Skips comments, bare timestamps and literals with `#{...}`. |
| `rust_string_literals` | Rust source | Raw (`r#"..."#`) and ordinary string literals that start like a log line. Format holes (`{}`, `{msg}`) become `<*>`. |

All three then replace, with `<*>`: URLs, e-mail addresses, timestamps, MAC addresses, IPv4 (with ports, keeping `<*>:<*>` or `<*>/<*>`), IPv6, hostnames ending in a common top-level domain, user names in known contexts (`user x`, `for x from`, `USER=`, `/home/x`, and similar), hex values and numbers. Templates that become nothing but placeholders are dropped and counted. Identical templates are merged.

Safety checks that fail the build: any dotted-quad or IPv6 address left in a template (private and documentation addresses too); a file that yields zero templates; a hash mismatch; a workdir or output path that is not git-ignored.

The scrubbing is best effort. It cannot prove every user name or host name is gone. That is one more reason the output is local-only.

## Using the derived registry with the cohort generator

`data/generator_v2.py` takes a registry path in its Python API (`generate`, `write_dataset`, `load_seed_catalog` all accept `registry_path`). Its command line has no `--registry` flag, and no edit was made to it. To load the local records next to the committed ones, build a merged file under `data/seeds_local/` and pass it in code:

```bash
cat data/seeds/registry.jsonl data/seeds_local/references_registry.jsonl > data/seeds_local/merged_registry.jsonl
uv run python - <<'PY'
from pathlib import Path
from data.generator_v2 import write_dataset
write_dataset(Path("data/seeds_local/cohort_with_local_seeds"), seed=42,
              registry_path=Path("data/seeds_local/merged_registry.jsonl"))
PY
```

Limits you must understand before relying on this:

* **No archetype uses the local templates yet.** The generator picks seeds from hard-coded template id lists (`ARCHETYPES`, `BOUNDARY_SEEDS`). Loading extra records is accepted and harmless, but no case will use them until a follow-up maps archetypes to local template ids. That change touches `data/generator_v2.py` and is a decision for the owner. The loader compatibility is covered by a test.
* **The generator does not yet mark such datasets.** Its manifest has no `contains_local_only_seed_text` field. If you ever do generate from the local registry, treat the whole output directory as local-only by hand. It must not be committed or published. Putting it under `data/seeds_local/` keeps it git-ignored.

## What you may and may not publish

* Do not commit or publish the fetched files, `references_registry.jsonl`, its manifest, `merged_registry.jsonl`, or any dataset built from the local registry.
* You may publish `references.json`, this tool and this guide. They contain no upstream content.
* You may quote results (counts, scores) from a run only if the report says the dataset was built from local-only seed text. Reports must still say the data is synthetic and not real telemetry (`AGENTS.md` rule 3).
* If you add a new reference, add its id, URL, 40-character commit, root license check, file paths and sha256 only. Put no sample line, not even a short one, in `references.json`, docs or tests. Tests use invented lines.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `... is inside a git repository and is not git-ignored` | Use a workdir or `--out` under `data/seeds_local/`, or add the path to `.gitignore`. |
| `could not fetch <sha> ... fetching by sha` | The host refused a by-sha fetch or the commit was removed upstream. Check network and proxy settings. Do not edit the pin without re-checking the license and hashes. |
| `exists at <sha>, expected <sha>` | A stale checkout in the workdir. Delete `data/seeds_local/fetched/<id>` and re-run `fetch`. |
| `sha256 mismatch for <path>` | The file differs from the pin (wrong commit, local edit, line-ending conversion). Delete the workdir entry and fetch again. If it still differs, upstream content at that commit changed; stop and report it. |
| `missing <path> (run fetch)` | Run `fetch` first, or the path does not exist at that commit. |
| `extractor ... produced no templates` | The file no longer looks like the format the extractor expects. Do not lower the check; fix the extractor or the reference. |
| `template contains a dotted-quad IP` | An extractor regression let an address through. Fix `normalize_body` and add a test with an invented line. |
| First clone is slow (Vector, Wazuh) | The fetch downloads tree metadata for the whole commit (blobs are fetched only for listed files). Allow a few minutes. |

## Verification status

Verified on this Linux host, 2026-10-04: real `fetch`, `verify` and `build` on all three sources at the pinned commits; every path in `references.json` exists at its commit and its sha256 matches; root `LICENSE` of each repository was read at the pinned commit (Apache-2.0, MPL-2.0, GPL-2.0 with OpenSSL exception). `build` wrote 40 records and the no-IP check passed.

Not verified: that the scrubbing removed every user name or host name; usefulness of these templates for any label or model result; anything about SecRepo, OpenEnv, ATT&CK or Zenodo; Apple Silicon (no hardware dependence expected, none tested).
