# Seed source licenses (WS5, partial)

Status: **GitHub-hosted sources checked 2026-10-04 by reading each repository's root `LICENSE` at the commit shown. Not legal advice.** Per-file headers inside fixture directories were not inspected. Sources not reachable from this environment are listed as unverified.

| Source | Commit checked | License (root `LICENSE`) | Copyleft? | Use in this repo |
| --- | --- | --- | --- | --- |
| `logpai/loghub` | `dd61d09` | Research/academic use; reference repo URL; cite ISSRE 2023 and ISSTA 2024 (D8) | No, but use-restricted | In use: templates only, notice shipped (`data/seeds/LOGHUB_LICENSE`) |
| `redcanaryco/atomic-red-team` | `388942a` | MIT | No | In use: 8 command seeds |
| `logstash-plugins/logstash-patterns-core` | `74a4098` | Apache License 2.0 (README states the same) | No | Candidate: copy allowed with license text and notices kept. Not yet added |
| `vectordotdev/vector` | `9aee1f5` | **Mozilla Public License 2.0** (not MIT or Apache) | File-level (weak) copyleft | Candidate: reuse of its files carries MPL file-level obligations. Prefer reference-only (URL + commit + sha256). Not yet added |
| `wazuh/wazuh` | `74ed87c` | **GNU GPL v2** (with an OpenSSL linking exception) | Strong copyleft | Do not vendor. Reference-only at most, until the owner accepts the risk |
| SecRepo (secrepo.com) | not reachable | **Unverified** | Unknown | Excluded |
| OpenEnv SRE triage (Hugging Face) | not reachable | **Unverified** | Unknown | Excluded (D6) |
| MITRE ATT&CK | not fetched | Unverified (terms of use) | Unknown | Technique IDs/names as metadata only; confirm before redistribution |
| Zenodo Loghub full logs | not reachable | Unverified | Unknown | Not used |

## Consequences

- The pasted claims that Wazuh, Vector and Logstash are all "Apache/MIT, unencumbered" are **wrong for Vector (MPL-2.0) and Wazuh (GPLv2)**. Only Logstash Patterns is Apache-2.0.
- Lab-only "no friction" advice does not apply: this repo is public and ships its registry (D9).
- Until the owner decides (reference-only vs vendoring), add no new source to `data/seeds/registry.jsonl` except Logstash Patterns after review.
- Reference-only sources store URL, pinned commit and sha256 and are fetched at build time into a git-ignored directory.
