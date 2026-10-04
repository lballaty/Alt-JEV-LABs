# Guide: testing with your own real events (optional)

Status: **guidance only. Nothing in this repo requires real data, and no real data is included.** The project's own results use synthetic cases and say so (D26). This guide is for anyone using the Alt-JEV-LABs framework who wants evidence about their own queue.

## Why bother

Synthetic and public-log cases (Loghub, Atomic Red Team, generator-authored) let you compare models fairly on a controlled task. They cannot show that a model works on your alerts: base rates, wording, duplicates, maintenance noise and surrounding context are all different. Only real, labeled events from your systems support a deployment conclusion, and even then only for those systems.

## What to collect

- **Events a team had to act on or dismiss:** single log lines, alerts, tool notifications, ticket descriptions, and optionally chat threads discussing them.
- **A realistic mix:** mostly routine noise, some real problems. Do not collect only dramatic incidents; that hides false-page cost.
- **Size:** aim for 200 to 300 events. Under about 100 will not separate close candidates.
- **Keep the context the real decision used:** change/maintenance windows, owner of the system, any already-open incident. The rubric (`docs/RUBRIC_V2.md`) decides from structured context, never from claims in the event text.
- **Set aside a small separate set of rare, high-impact events** (true must-page incidents). Report it on its own; do not average it into the pooled result.

## Before you use it

1. **Permission.** Confirm you may use the data for testing. For customer or partner data, get written agreement. If unsure, do not use it.
2. **De-identify.** Remove or pseudonymize people, hosts, addresses, tokens and keys. Chat can go through `ingest/chat.py` (`deidentify_raw_thread`; off by default, see `docs/CHAT_MODULE.md`). **This repo has no de-identification tool for plain logs or alerts yet.** Use your own, then have two people spot-check a sample. The chat tool's own limits (names in free text, phone numbers, URL identifiers) are listed in `docs/CHAT_MODULE.md`.
3. **Keep it out of Git.** Never commit real events, even de-identified. Keep the pseudonym salt private and out of Git (the salt in `configs/chat_module.json` is a public fixture value, not for real data).

## Labeling

- Two people label each event **independently** against the frozen rubric (`docs/RUBRIC_V2.md`) without seeing each other's labels or any model output.
- Record every disagreement in an **adjudication log**. An unresolved event stays `needs_adjudication`; it is never silently turned into a gold label.
- Report agreement between the two labelers. Low agreement means the rubric or the data is unclear, not that a model is wrong.
- Split by event group (an incident and its repeats stay together) and seal the test split before looking at any model.

## Reporting

Every report that uses real events must:

- label the dataset **real (de-identified)** and keep it separate from synthetic results;
- state the count, source type, collection period and de-identification method, without revealing identities;
- give counts and confidence intervals, not bare percentages;
- not claim the result transfers to other systems.

## What is not built

- A loader and runner path for real data (the v2 loader reads the generator's synthetic cases; real-data intake is future work, formerly WS6).
- A log/alert de-identification tool.
- Labeling and adjudication-log tooling.

If you need these, open an issue or tracker item before building them, and keep the rules above.

A model passing a test on real events is evidence for a human decision. It is not an approval to enable any automatic action (`AGENTS.md` rule 5).
