# Realism research for synthetic tests (WS10)

Status: **In progress — first pass, 2026-09-30.** No internal or customer data exists (tracker Q9), so realism rests on public evidence only.

## Method and evidence levels

This environment's network policy allowed only GitHub. Survey reports and papers (usenix.org, arxiv.org, acm.org, microsoft.com, sans.org and others) were blocked. Every figure below therefore carries one of two evidence levels:

| Level | Meaning | Use in the generator |
| --- | --- | --- |
| **Verified** | Measured by us from a public dataset at a pinned commit; the script and numbers are reproducible | May set a parameter directly, with the citation |
| **Lead (unverified)** | Text returned by a web search; the primary document was **not** opened | Must not set a parameter until the primary source is read. It can guide a range marked "assumed" |

To finish verification, allow these hosts in the environment's network settings (or run on the Mac): `usenix.org`, `arxiv.org`, `dl.acm.org`, `ieeexplore.ieee.org`, `www.microsoft.com`, `www.sans.org`, `www.pagerduty.com`.

## Verified findings (public datasets)

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

This is one supercomputer's logs and a small sample, so it is not a general base rate. It supports the direction, not a number: most log lines are not alerts.

## Leads to verify (search results only, primary sources not opened)

| Claim as returned by search | Stated source | Why it matters |
| --- | --- | --- |
| 46% of SOC alerts are false positives and 42% are never investigated. Survey of 300 security professionals at organisations with 750+ staff (US, UK, AU, NZ), fielded June–July 2025, published February 2026 | Microsoft/Omdia "State of the SOC" ([Microsoft Security blog](https://www.microsoft.com/en-us/security/blog/2026/02/17/unify-now-or-pay-later-new-research-exposes-the-operational-cost-of-a-fragmented-soc/)) | Share of benign/false alerts in the security stream |
| Most "false positives" are benign triggers: true alarms explained by legitimate activity. Qualitative study: survey of 20 plus interviews with 21 SOC practitioners | AlAhmadi, Axon, Martinovic, "99% False Positives", USENIX Security 2022 ([USENIX](https://www.usenix.org/conference/usenixsecurity22/presentation/alahmadi)) | Our "benign but real" cases (W1, W4) should dominate the benign share, not random noise |
| 73% of security teams name false positives their top detection challenge; "very frequent" false positives rose from 13% to 20% year over year | SANS 2025 Detection & Response Survey, via a vendor blog ([Stamus Networks](https://www.stamus-networks.com/blog/what-the-2025-sans-detection-response-survey-reveals-false-positives-alert-fatigue-are-worsening)); the primary survey was not read | Supports a high benign share; secondary source |
| Up to 53% of security alerts are false positives | Devo 2024 SOC Performance Report, as quoted by a vendor article ([secure.com](https://www.secure.com/blog/soc/soc-alerts)) | Same; secondary |
| The median on-call team receives over 300 alerts per week | PagerDuty State of Digital Operations, as quoted by a blog ([DEV Community](https://dev.to/devhelm/alert-fatigue-why-your-team-ignores-pages-and-how-to-fix-it-671)) | Stream volume for the S6 replay suite |
| Alert storms (many alerts from one failure) happen about once a week in a bank's production systems, and take several engineers about an hour each | Zhao et al., "Understanding and Handling Alert Storm for Online Service Systems", ICSE-SEIP 2020 ([IEEE](https://ieeexplore.ieee.org/document/9276598/)) | Storms and duplicates must be in the stream; supports W7-type attach cases |

The claim "2,992 alerts per day, 63% unaddressed" appeared in search results without a traceable primary source and is **not used**.

## Proposed generator parameters (WS3)

| Parameter | Proposal | Basis | Status |
| --- | --- | --- | --- |
| Source-severity field on generated security alerts | Draw from the Sigma/Elastic mix: about 1–2% critical, 28–45% high, 43–47% medium, 9–24% low | Verified §1 | Usable now |
| Source severity vs rubric answer | Many "high"-severity source alerts must be benign or retained under the rubric, so over-trusting source severity costs accuracy. Target: about half of high/medium security alerts benign | Verified §1 (content skew); benign share from leads | Share **assumed** until leads are verified |
| Security technique mix | Weight seeds by tactic counts in §3; keep the tactic label and ATT&CK version per case | Verified §3 | Usable now |
| Platform mix | Add Windows event log and cloud audit (AWS CloudTrail, Azure activity) formats; target at least 30% non-Linux security cases | Verified §2 gap | Needs new seeds (WS1 follow-up) |
| SRE alert severity field | About 60–70% warning, 25–40% critical, under 5% info | Verified §4 | Usable now |
| Benign share of the S6 stream | 40–60% of security-origin alerts benign, mostly benign triggers | Leads (Omdia, AlAhmadi, SANS, Devo) | **Assumed** until verified |
| Must-page prevalence in S6 | At most a few percent of events | Direction from verified §5 and the leads | **Assumed** |
| Storms and duplicates in S6 | At least one storm (one failure producing many related alerts) per simulated week, plus exact repeats while an incident is open | Lead (Zhao et al. 2020) | Frequency **assumed** until verified |
| S6 volume | On the order of 300+ alerts per team-week | Lead (PagerDuty) | **Assumed** |

## Next steps

1. Allow the blocked hosts, or run on the Mac, and read each lead's primary source. Promote verified figures to parameters and correct or drop the rest.
2. Add Windows and cloud audit seeds to the registry, with pinned commits and license terms (candidates to evaluate: OTRF Security-Datasets, Splunk attack_data).
3. Realism check once the generator exists: compare generated distributions against the verified figures above, and have a practitioner blind-rate a mix of generated and real public samples.
4. Every report states which parameters are verified and which are assumed.

## Reproduction

```bash
git clone --depth 1 https://github.com/SigmaHQ/sigma                 # 07ec293
git clone --depth 1 https://github.com/elastic/detection-rules       # 94dc9b5
git clone --depth 1 https://github.com/prometheus-operator/kube-prometheus   # 799f3d7
git clone --depth 1 https://github.com/samber/awesome-prometheus-alerts      # 70cdf97
git clone --depth 1 https://github.com/logpai/loghub                 # dd61d09
```

Counts were produced by regex over rule files: Sigma `level:` and `product:`, Elastic `severity =`, Prometheus `severity:`, tactic tags and names. The BGL/Thunderbird figures come from the `Label` column of the `*_2k.log_structured.csv` samples. A reusable script is a WS10 follow-up.
