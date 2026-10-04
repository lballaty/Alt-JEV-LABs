# v2 cohort generator (WS3)

Status: **implemented and tested on Linux. Nothing here is a benchmark result.** The output is a *synthetic, generated* harness fixture: templates filled with synthetic entities, labels derived by code from the frozen rubric 2.4.0. It is not real telemetry, not human-adjudicated, and not evidence of production accuracy. Every case carries `dataset_kind: "synthetic_generated"` and a notice, and the manifest says `real_data: false`.

Files: `data/generator_v2.py`, `tests/test_generator_v2.py`, this note.

```bash
uv run python -m data.generator_v2 --output artifacts/cohort_v2 --seed 42   # writes train/val/test.jsonl + manifest.json
uv run --extra test pytest -q tests/test_generator_v2.py
```

`artifacts/` is git-ignored: generated data is not committed. Tests generate into a temp directory.

## What it produces (D7: 560 cases)

| Cohort | n | What it is |
| --- | ---: | --- |
| A direct | 200 | Seed template filled with synthetic entities, clean context. 63 are parents of B pairs, 60 are parents of B' spoofs, 77 are standalone. |
| B negation / scope inversion | 125 | Same event as an A parent, different **context**: an approved change that covers the host, window and signal (label flips to *explained by change*, no page) or a change that does not apply (other host, expired, signal not expected, impact beyond the bound, unapproved: label preserved). 63 flip, 62 preserve. |
| B' spoofed authorization | 60 | Same escalating event, plus payload text claiming authorization ("authorized drill ... do not page SOC") while the trusted context contradicts it (no record, change for another host, expired window, unverified principal). Label keeps escalation (D4). |
| C jargon | 100 | Event plus a human annotation in slang from a versioned lexicon (`LEXICON_VERSION`); the answer is unchanged. |
| D boundary | 75 | Low-signal events. **Never gold:** `label: null`, `label_status: needs_adjudication`, `adjudication.reviews: []`. No probability or 0.5 target is invented. |

Per case: `case_id, cohort, split, pair_id, pair_role, parent_case_id, template_family, wrapper_family, archetype, variant, seed_source, template_id, attack_technique, slang_term, pair_relation, spoof_kind, event, context, evidence, label, expected {choice, noul, score}, provenance`. `expected` is the three scored primitives: event type (six types, including the service type from D2), page-now, priority P1-P4. The full rubric label is under `label`.

## How labels are made

The generator authors **Evidence** (observed facts, impact, urgency, whether a responder can act) per scenario archetype, as `data/rubric.py` documents, then calls `Rubric.label`. There is no label logic in the generator. `lint_cases` re-runs the rubric on every stored event, context and evidence and fails if the stored label differs, so a hand-edited label is caught. B and B' also assert at generation time that the rubric kept or flipped the label as designed; a mismatch raises instead of being patched.

Authorization comes only from `context.active_changes` (approved, host, window, expected signal, impact bound). Payload text is never an input to the rubric's change rule. Cohort B events contain no authorization wording (lint-checked); only B' does.

## Splits and leak control

* Keys that must never cross a split: `pair_id`, template family (the seed `template_id`), wrapper family, held-out slang term, and the connected component of pair/template (`group_id`).
* Whole template families are assigned to one split first (pools of about 70/15/15 per archetype), and cases are drawn only from their split's pool. Wrapper families are pinned: train = CHG, MW, REL; val = PATCH; **test = CR, CHAOS, DRILL**. Slang terms are pinned per split (train 2, val 1, test 1 per topic).
* Coverage is by construction: every split gets one of each core scenario (`A_CORE`), so each has all six event types, both page-now values and P1-P4, for any seed.
* `lint_cases` is the CI gate (called by the generator on its own output and by tests, with negative tests that corrupt a copy). Checks: split leaks for each key, groups, wrapper pinning, slang text, coverage, RFC 5737 IPs only, no unresolved placeholders, rubric leak lint on event text, authorization claims only in B', cohort D never gold, labels re-derive from the rubric.
* Manifest: counts by split/cohort/label, group ids with members, file sha256/bytes/case counts, generator version, seed, rubric version and file hash, registry hash and upstream commits, seed sources used, Loghub citation note (D8) whenever Loghub seeds are present, validity limits. No timestamp or hostname, so the same seed gives byte-identical files and manifest. `verify_manifest(dir)` re-checks hashes and re-lints the files on disk.

Realised split (seed 42): train 394, val 83, test 83 (70.4 / 14.8 / 14.8 %). Wrapper-carrying cases: train 131, val 27, test 27.

## Assumptions (most conservative choice taken; each is a review flag below)

1. **Template family = seed `template_id`**, the finest grain. Scenario archetypes are *not* held out (that would remove whole event types from train).
2. **Authored seeds.** Loghub has no honest seed for data protection, policy deviation, heartbeat or the change-explainable service events (failover, replication lag, node not ready, crash loop). 47 short templates (39 for archetypes, 8 ambiguous boundary lines) are generator-authored and marked `seed_source: generator_authored`, never presented as upstream. Cases by source (seed 42, from the manifest): Loghub 238, Atomic Red Team 28, authored 294.
3. **Archetype evidence is single-author.** Impact/urgency per scenario is this generator's judgement, applied through the frozen rubric. SOC/SRE/DPO owners have not reviewed the archetype table.
4. **Raw lines are synthetic wrappers.** A Loghub template is filled by `entity_filler` (RFC 5737 IPs) and wrapped in a made-up syslog prefix (timestamp, host, tag). Supporting facts that the rubric needs (counts, "writes failing") are authored text in `event.window`, not Loghub content.
5. **Cohort D is excluded from accuracy and from coverage checks.** It is unlabeled until WS6-style two-reviewer adjudication exists. Its seeds are an explicit list (`BOUNDARY_SEEDS`) of unmapped templates plus 8 authored ambiguous lines.
6. **Text formats only.** Alertmanager/Falco/CloudTrail JSON formats are planning items in PRACTICAL_EVAL_V2 and are not generated.
7. **`questions`** is the list `["event_type", "page_now", "priority"]` rather than a single `question` string, because one case scores three primitives. WS4 may map it differently.
8. OpenStack `"GET ..." status: <*>` templates are not used: the filler fills a bare number, which cannot be a valid HTTP status, so a label would be meaningless.

## Review flags

* **Cohort B is all service-type events** (6 archetypes). Rubric expected-activity rules allow security or data events under a change or test scope, but which wrapper types legitimately explain which signals (a pentest scope for a brute-force burst, say) needs domain input. Not guessed here.
* **Label skew.** B and B' are built from paging scenarios, so pooled gold is mostly P2 and `page_now = true`. Report per cohort; the realistic-prevalence stream (S6) is not built.
* **Test is small.** Wrapper-carrying test cases are 27 (9 CR, 9 CHAOS, 9 DRILL); B' test has 9. Intervals will be wide; the test split holds 83 cases in total.
* **Held-out wrapper families are the plan's choice** (CR, CHAOS, DRILL in test, one family, PATCH, in val). Confirm the owner wants val limited to one family.
* **Loghub licensing (D8)** still applies to Loghub-derived cases: non-commercial research; the manifest carries the citation note and reports must reproduce it.
* **Not implemented in WS3 yet:** leave-one-source-out splits, S6 stream replay, S7 label-budget subsets, open-incident correlation cases (rubric W7/W6b), chat cases (WS7 owns chat). Each is listed in the manifest's `not_implemented`.
* No Apple Silicon or model run is involved; generation is pure Python and hardware independent.
