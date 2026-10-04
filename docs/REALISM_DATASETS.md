# Public dataset candidates for realism work

**Type:** Living source inventory (WS10).  
**Owner:** `codex-ebook-companion-01`  
**Inspected:** 2026-10-04 through GitHub metadata, README and LICENSE files. No raw-log import, operational labeling, or model run performed.

## Candidate inventory

| Candidate and pinned revision | Relevant material | Observed license declaration | Current disposition |
| --- | --- | --- | --- |
| [OTRF/Security-Datasets](https://github.com/OTRF/Security-Datasets/tree/d9d40ef123d2c87d5d3df28c96bcab4f0faccc87) | Windows attack artifacts, malicious/benign dataset description, AWS scenario metadata | Root LICENSE is MIT; README also retains a GPL-3.0 section | Hold import until artifact-specific declaration conflict is resolved |
| [splunk/attack_data](https://github.com/splunk/attack_data/tree/a92cc4e6d7e39d56a0840d206a0963eeee0e22db) | Windows Security/Sysmon examples, AWS CloudTrail and Azure simulation descriptors | Root LICENSE is Apache-2.0 | Candidate for artifact-level review; no blanket dataset clearance asserted |
| [NetManAIOps/OpsEval-Datasets](https://github.com/NetManAIOps/OpsEval-Datasets/tree/13e04f574c2a1c6f30005af346ef4a56402d3f2e) | English/Chinese operations QA and alert-summary task description | Root LICENSE is MIT; README metadata says apache-2.0 | Hold import pending clarification; QA tasks are not a chronological alert stream |
| [CloudWise-OpenSource/GAIA-DataSet](https://github.com/CloudWise-OpenSource/GAIA-DataSet/tree/238a9e24ae0b69e7e05dff112652a3fa62db88fd) | Simulated service workload with logs, metrics, traces and injected anomalies | Root LICENSE is GPL-2.0 text; README elsewhere states Apache-2.0 | Hold import pending clarification; injected faults are not natural incident prevalence |

These are observations of repository declarations, not legal conclusions. Keep third-party terms separate from this project's own code/docs licenses. Dataset entry existence does not prove raw content was obtained or checked.

## Concrete review candidates

### Splunk

At the pinned revision, the tree contains:
- `datasets/attack_techniques/T1003.003/atomic_red_team/4688_windows-security.log`
- `datasets/attack_techniques/T1078.004/aws_login_sfa/cloudtrail.json`
- `datasets/attack_techniques/T1078.004/azure_ad_service_principal_authentication/azure_ad_service_principal_authentication.yml`

The Azure descriptor says tenant details were replaced, but its `sourcetype`/`source` are `linux_secure`. Treat this as a metadata review issue: inspect the actual event format before calling it Azure audit telemetry.

The README uses Git LFS. Avoid downloading the whole repository's LFS data; fetch a selected pinned artifact, verify it is actual content rather than a pointer, and record its content hash. Windows attack captures broaden syntax but cannot establish benign/attack base rates.

### OTRF

The inspected `datasets/atomic/_metadata/SDAWS-200914011940.yaml` describes an AWS attack simulation and points to an archive. Metadata includes adversary command output and credential-shaped fields. Do not copy that output into fixtures or reports. Inspect archives in an isolated scratch location and synthesize replacement identities, account IDs, host names and credentials before proposing seeds.

No OTRF archive was downloaded in this audit. Its README license conflict must be settled first.

## Evidence types must remain separate

| Evidence type | Supports | Does not establish |
| --- | --- | --- |
| Detection rules | Format/technique coverage and source-severity stress cases | Fired-alert class shares |
| Attack simulations | Specific event shapes and known injected attack context | Typical operational prevalence |
| Service simulation with fault injection | Temporal correlations and controlled fault episodes | Production incident frequencies |
| Operations QA | Task vocabulary and separate knowledge tests | Triage routing accuracy on ingress events |
| Independent real target-stream labels | A scoped assessment in that environment | Universal future correctness |

## Import checklist for Claude's seed implementation

1. Pin the revision, artifact path, acquisition method and SHA-256 of actual content.
2. Inspect all applicable notices and dataset-specific licenses; stop on conflicts.
3. Identify whether labels describe attack activity, log anomalies, incident relevance or response requirements.
4. Replace identifiers and credential-shaped material; do not commit raw traces.
5. Create paired context cases without duplicating the same template family across splits.
6. Retain source attribution and report synthetic transformations.
7. Run seed/leak/privacy checks and update the shared tracker in the implementation PR.

This inventory does not claim WS5 completion, alter the rubric, or import data into the registry.
