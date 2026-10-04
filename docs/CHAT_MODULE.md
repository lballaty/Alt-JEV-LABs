# Chat module (WS7, suite S9)

Status: **implemented, tested on Linux with synthetic data only.** Nothing here is a benchmark result. The module is **off by default**.

Design source: `docs/PRACTICAL_EVAL_V2.md` section 3a and decisions D4 and D5.

## Files

| File | Purpose |
| --- | --- |
| `configs/chat_module.json` | Toggle (`enabled: false`), salt label, caps. Not in `benchmark_config.yaml`. |
| `ingest/chat.py` | Schema, de-identification, synthetic threads, case builder |
| `tests/test_chat_ingest.py` | 30 tests |

Nothing in `data/`, `evaluation/`, `models/` or `training/` imports `ingest` (a test checks this), so disabling the module changes no core behaviour. The runner (WS4) is expected to do `if chat.is_enabled(): add S9`, and to report S9 separately from S1-S8.

## Thread schema

`ChatThread`: `thread_id`, `channel` (pseudonym or fixture name), `channel_kind` (`incident_bridge`, `team_channel`, `support_queue`), `messages`, `dataset_kind` (`synthetic` or `real_deidentified`), optional `event_ref` (`{"kind", "id"}` such as `INC-1234`), truncation counters, `pair_id`, `scenario`, `provenance`.
`ChatMessage`: ISO-8601 timestamp with timezone, `role` (closed list), `author` (pseudonym `user-xxxxxxxx`), `text`.

A thread cannot be built as raw chat: `dataset_kind` must be one of the two safe values, and raw exports enter only through `deidentify_raw_thread`. Unknown keys, unknown roles, naive timestamps and out-of-order timestamps raise `ChatSchemaError`.

## De-identification

Raw input is an allow-listed object (`thread_id`, `channel`, `channel_kind`, optional `event_ref`, `messages[{ts, author, role, text}]`). Replacements are deterministic from `(salt, category, value)`:

| Found | Becomes |
| --- | --- |
| author, `@handle`, names in `known_users` | `user-<8 hex>` |
| email | `user-<8 hex>@example.com` |
| hostname with a listed suffix, names in `known_hosts` | `host-<8 hex>.example.net` |
| IPv4 (not already RFC 5737) | an address in `192.0.2.0/24`, `198.51.100.0/24` or `203.0.113.0/24` |
| IPv6 | `2001:db8::xxxx` (RFC 3849) |
| keys, tokens, JWTs, bearer values, `password=`-style values, PEM private keys, 32+ hex, 40+ opaque characters | `[REDACTED_SECRET]` |
| thread id, channel name | `thread-<hex>`, `channel-<hex>` |

After replacement the text is re-scanned; any residue raises `DeidentificationError` (the message names categories, never the text). Length caps run after de-identification so a cap cannot cut a secret in half.

`DeidReport` records counts and distinct pseudonym counts per category, truncation counts, and a `not_detected` list. It never holds an original. Only the salt's 8-character fingerprint is stored in provenance.

## Synthetic threads (S9 fixture)

`generate_synthetic_threads(config, seed=, groups=)` returns `2 * groups` threads. Each group is a minimal pair with one `pair_id`: a base thread from six families (human report without alert, pasted log line, ticket follow-up, sarcasm, resolved-then-reopened, routine chatter) and a twin with one extra message from an `unknown` role claiming approval and "ignore the alerts" (chat B-prime). Pasted log lines come from Loghub templates in `data/seeds/registry.jsonl` filled by `data/entity_filler.py`. Output depends only on `(seed, groups, registry bytes)`.

Every thread says `synthetic: true`; provenance carries the generator, seed, registry sha256, seed template id and the Loghub attribution note (D8: reports using it must cite as in `data/seeds/README.md`). Messages are lint-checked against the rubric's forbidden answer phrases; only the spoof message uses the exempt `B_prime` cohort.

**Threads are unlabeled.** `label_with_rubric` forwards caller-supplied `Evidence` to `data.rubric.Rubric.label` (2.4.0) and ignores the chat text. The module never chooses a type, impact or urgency.

## Trust rule (D4)

Chat text is untrusted. "Approved", "authorized", "it's a drill", "don't page" in a message are claims from an unverified speaker. They are never read into the context: `build_context` accepts structured arguments only, and `to_case` takes the context as a separate input. `find_authorization_claims` flags such wording (pattern name and message index, no text) into `case["meta"]`. `meta` has `show_to_model: false`: **the runner must not put `meta` in the prompt.** `event_ref` is only a claim; `meta.event_ref_found_in_structured_context` says whether the id exists in the structured incident or change lists. Classifier output on a chat case still authorizes nothing (AGENTS.md rule 5).

## Verified vs not verified

| Item | Status |
| --- | --- |
| 30 module tests; full suite 105 passed (75 existing + 30) on Linux | Verified |
| Sentinel IPs, emails, hosts, handles and secrets absent from de-identified output and report (synthetic sentinels) | Verified in tests |
| Determinism of de-identification and generation | Verified in tests |
| Recall of de-identification on real chat | **Not verified.** No real chat was used. Patterns are heuristic |
| Any model result on S9 | **Not run.** The suite is not registered in a runner (WS4) |
| Apple Silicon / hardware-dependent steps | Not applicable, not run |

## Assumptions (conservative choices)

- Off by default; a string `"true"` in the config is rejected.
- Roles come from the caller. An unknown role is an error, not mapped to `unknown`.
- Empty messages are rejected rather than skipped.
- Over-redaction is accepted: any dotted quad up to 255 (including a version like `1.2.3.4`), any 32+ hex string (including a file hash) is replaced.
- Thread cap keeps the **most recent** messages; per-message cap cuts the end. Both are counted in the thread and report.
- The config salt is public, so pseudonyms from it are guessable for common names. It is for fixtures only.
- Synthetic contexts have no incidents or changes; threads carry no label.

## Review flags

1. **Real-chat de-identification is unproven.** Personal names in free text, phone numbers, addresses, dotless hostnames and URL-path identifiers are not detected unless listed in `known_users`/`known_hosts`. Two-person spot-check of every real thread before it is stored or committed (also WS6).
2. **Use a private salt for real data** (`salt=` argument), kept out of Git. Decide where it lives.
3. **Timestamps are kept** (needed for change-window logic). They can help re-identify; decide whether to shift per thread.
4. **Model input has roles only**, not author pseudonyms, as in section 3a. Two speakers with one role cannot be told apart. Add a per-thread speaker index if S9 needs it.
5. **Thread cap keeps the newest messages**; the opening report may be lost. Choose the cap (default 40 messages, 2000 characters) after seeing real thread lengths.
6. **IPv4 pseudonym space is 762 addresses**, so collisions merge identities.
7. **Incident-dedup and incident-correlation cases** (thread references an open incident) need structured incident records that include type, impact and priority, which are labels. They were not authored here; WS3/WS4 should add them under the rubric.
8. **S9 registration and reporting** are WS4 work. Required there: S9 reported separately, synthetic and real labeled, `meta` never shown to the model, Loghub citation.
9. The spoof wording set (two sentences) is small; extend it with practitioner phrasing before drawing conclusions about spoof recall.
