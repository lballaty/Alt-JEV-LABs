# Realism research for synthetic tests (WS10)

Status: **In progress — primary-source audit updated 2026-10-04; target-stream validation remains open.** No internal or customer data exists (tracker Q9), so realism rests on public evidence only.

## Method and evidence levels

The first session's shell egress was restricted. On 2026-10-04, this session read primary sources through web retrieval and dataset metadata through GitHub. These are different access paths: success through retrieval does not prove shell access or model-host access.

| Level | Meaning | Permitted use |
| --- | --- | --- |
| Inherited measurement | Previous session counted repository content; original counts retained below, not rerun by this session | Content/coverage inventory only until reproduced from pinned sources |
| Primary source read | Study/report and its population or denominator inspected | Design relevant cases; use numeric rates only with matching scope and explicit limitations |
| Scenario assumption | A chosen synthetic test setting without target-stream measurements | Sensitivity analysis, labeled as assumed |
| Unverified lead | Only a secondary account or search snippet available | Research lead only; not a measured default |

**Denominator rule:** rule counts, log-line anomaly labels, fired alerts, incidents, pages and responder interruptions are different units. Never substitute one for another. Source severity is also distinct from the frozen rubric's priority and notification answers.

## Inherited public-content measurements (2026-09-30)

### 1. Security detection content skews to "medium" and "high" severity

Rule counts by the rule author's declared severity:

| Source (commit, date) | Rules | Critical | High | Medium | Low | Informational |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SigmaHQ/sigma `07ec293` (2026-09-25), `rules/` | 3,144 | 71 (2%) | 1,420 (45%) | 1,354 (43%) | 274 (9%) | 25 (1%) |
| elastic/detection-rules `94dc9b5` (2026-09-29), `rules/` | 2,165 | 23 (1%) | 603 (28%) | 1,012 (47%) | 527 (24%) | — |

This is the distribution of *rules*, not of fired alerts. Alert-volume shares depend on how often each rule fires, which these repos do not show.

### 2. Public security content is mostly Windows

Sigma rules by `logsource.product`:

| Product | Windows | Linux | Azure | macOS | AWS | GCP | Other/none |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 2,410 (77%) | 210 (7%) | 123 (4%) | 69 (2%) | 57 (2%) | 26 (1%) | 249 (8%) |

**Realism gap:** our seed registry (WS1) is Linux and Hadoop/OpenStack log templates plus eight Linux Atomic Red Team tests. It has no Windows event logs and no cloud audit logs.

### 3. ATT&CK tactic mix, and a taxonomy change

Rules tagged per tactic (a rule can carry several):

| Tactic | Sigma | Elastic |
| --- | ---: | ---: |
| Execution | 800 | 510 |
| Persistence | 725 | 525 |
| Privilege escalation | 656 | 387 |
| Stealth / Defense evasion (see below) | 944 (stealth) + 378 (defense impairment) | 727 (Defense Evasion) |
| Credential access | 352 | 319 |
| Discovery | 248 | 198 |
| Command and control | 247 | 245 |
| Initial access | 203 | 282 |
| Impact | 154 | 139 |
| Lateral movement | 145 | 150 |
| Collection | 110 | 113 |
| Exfiltration | 77 | 96 |

Current Sigma rules tag `attack.stealth` and `attack.defense-impairment` where older content used Defense Evasion. Elastic still uses Defense Evasion. The seed registry and reports must record which ATT&CK version they use.

### 4. Operational (SRE) alert rules are mostly "warning"

| Source (commit, date) | Alert rules | Critical | Warning | Info | None |
| --- | ---: | ---: | ---: | ---: | ---: |
| prometheus-operator/kube-prometheus `799f3d7` (2026-09-24), `manifests/` | 139 | 34 (24%) | 96 (69%) | 7 (5%) | 2 (1%) |
| samber/awesome-prometheus-alerts `70cdf97` (2026-09-18), `_data/rules.yml` | 1,162 | 453 (39%) | 677 (58%) | 32 (3%) | — |

### 5. Anomalies are a small minority of log lines

logpai/loghub `dd61d09` labeled 2,000-line samples:
- **BGL:** 143 of 2,000 lines are alert-tagged (**7.15%**).
- **Thunderbird:** 0 of 2,000 in its sample.

This is one supercomputer's logs and a small sample, so it is not a general base rate. It characterizes those sampled log lines only. It cannot establish must-page prevalence among the already-filtered alerts entering our gateway.

## Primary-source audit (2026-10-04)

### Microsoft/Omdia: a surveyed estimate, not observed gateway truth

The [Microsoft report summary](https://www.microsoft.com/en-us/security/blog/2026/02/17/unify-now-or-pay-later-new-research-exposes-the-operational-cost-of-a-fragmented-soc/) reports an estimated 46% false-positive share and 42% uninvestigated alerts. Its footnote identifies 300 SOC-responsible professionals at organizations over 750 employees, in the US, UK, Australia and New Zealand, surveyed June 25–July 23, 2025. The detailed gated report and raw data were not obtained.

These are vendor-commissioned survey estimates. The two percentages must not be added: uninvestigated alerts have no established truth label, and the summary does not give disjoint categories. A 40–60% benign-alert scenario is a plausible sensitivity choice, not a validated default for our stream.

### Alahmadi et al.: distinguish benign triggers from detector errors

The [USENIX paper](https://www.usenix.org/system/files/sec22-alahmadi.pdf), §§1, 6 and 9, uses a 20-person survey and 21 interviews across seven SOCs. It distinguishes alarms that incorrectly indicate an event from accurate detections of legitimate activity. Its title is not a universal 99% measured false-positive rate. The authors identify small, non-random, mainly European/UK participation and self-report limitations.

Design matched benign/malicious cases whose observed event is similar but trusted context differs. Preserve separate truth for the observed event and the response decision; do not equate a real detected event with a required page. The study supports this taxonomy, not a numeric benign-trigger mixture for our test stream.

### Zhao et al.: correlated bursts are necessary test cases

The [author-hosted ICSE-SEIP paper](https://netman.aiops.org/wp-content/uploads/2020/07/AlertSummary_CR.pdf), §2, studies a bank's alert data and surveys 44 engineers; 86.3% report storms roughly weekly. It describes ordinary and bursty periods and correlated alerts with unrelated background noise.

Use quiet/bursty periods, downstream correlations and unrelated interleaved alerts. Weekly storms are a study-specific scenario anchor, not a universal lower bound. Include a genuinely new urgent event during an existing incident so grouping cannot hide it. No performance result from that study is a result for Alt-JEV-LABs.

### PagerDuty: correct the unit and drop the unsupported weekly median

The [2022 primary report](https://www.pagerduty.com/state-of-digital-ops-2022/) describes a median of two off-hours interruptions per responder per month for its 2021 analysis. Its unit is not total alerts per team-week. The earlier secondary claim of a 300-alert weekly team median was not verified in the primary material inspected.

Remove 300/week as an evidence-backed default. Select an explicitly assumed load envelope and measure saturation on the target hardware; never convert responder interruptions to ingress throughput.

### Remaining leads

SANS/Devo percentages and the untraceable “2,992 alerts/day” claim are not used as generator inputs. Primary verification remains open if they later add information beyond the inspected sources.

## Generator guidance and acceptance boundaries

This is research guidance for Claude's WS3 implementation. It does not alter the frozen rubric or silently change sealed data.

| Parameter | Research treatment | Evidence limit |
| --- | --- | --- |
| Source severity | Stress both concordant and conflicting source severity versus rubric response | Rule-library counts show authored content, not firing rates |
| Tactic/platform coverage | Add Windows and cloud formats after artifact-level review; preserve source versions | Library coverage cannot prescribe event prevalence; 30% non-Linux remains a design choice |
| Benign share | Evaluate several explicitly assumed mixtures; keep benign triggers separate from detector errors | Omdia's 46% is surveyed, population-specific and definition-sensitive |
| Uninvestigated share | Missing/unknown truth may be tested separately | Uninvestigated does not mean benign or malicious |
| Must-page prevalence | Sweep assumed rare-to-less-rare scenarios; report sample counts and uncertainty | Loghub log-line anomaly shares do not estimate page prevalence |
| Storms/duplicates | Test repeated alerts, correlated downstream failures, unrelated noise, and new urgent events | Weekly storms may anchor a scenario; frequency remains target-dependent |
| Stream load | Define assumed arrival rates, burst sizes and durations; measure backlog and latency | No verified universal 300-alert/week median |
| Class/cohort mix | Preserve D1/D7 pilot design and report its constructed nature | Coverage-balanced pilot proportions are not production prevalence |

Each chosen parameter should record: name, unit/denominator, value or range, evidence level, source URL and version, population/time window, transformation applied, and owner acceptance where needed. Unknown deployment prevalence means no “realistic distribution validated” claim.

## Dataset candidates and import gates

See [REALISM_DATASETS.md](REALISM_DATASETS.md) for pinned Windows/cloud/SRE candidates. No raw telemetry or seeds were imported in this audit. Licensing conflicts and artifact-level privacy checks remain import gates. Attack simulations and educational QA corpora can broaden formats; they do not provide a representative operational SOC queue.

## Remaining work

1. Reproduce inherited rule/content counts using full commit pins and a checked parser; a reusable repository script is implementation work owned by Claude.
2. Resolve artifact-level license declarations, inspect selected samples locally, and replace identifying fields before seed import; retain provenance and notices.
3. Compare generated case coverage, fields, correlations and burst behavior with the inspected sources. Report scenario assumptions separately from observed properties.
4. Obtain independent practitioner assessment of a blind generated/public-example sample. This is not performed yet.
5. Target-environment labels and a monitored pilot remain required for deployment claims. No internal/customer source is currently available (Q9).
6. Expand source coverage if needed; successful web retrieval does not remove shell or model-host egress restrictions.

## Reproduction

```bash
git clone --depth 1 https://github.com/SigmaHQ/sigma                 # 07ec293
git clone --depth 1 https://github.com/elastic/detection-rules       # 94dc9b5
git clone --depth 1 https://github.com/prometheus-operator/kube-prometheus   # 799f3d7
git clone --depth 1 https://github.com/samber/awesome-prometheus-alerts      # 70cdf97
git clone --depth 1 https://github.com/logpai/loghub                 # dd61d09
```

Inherited counts were reported as produced by regex over rule files: Sigma `level:` and `product:`, Elastic `severity =`, Prometheus `severity:`, tactic tags and names. The BGL/Thunderbird figures come from the `Label` column of the `*_2k.log_structured.csv` samples. A reusable script is a WS10 follow-up.

The shallow-clone commands above are discovery commands, not exact reproduction commands: their comments do not pin checkout. Fetch the full recorded revision and check it out detached before counting, record parser/version and output hashes, and fail if the requested revision is unavailable. The counts have not been independently rerun in this session.
