"""WS3 cohort generator tests, including the CI leak lint.

Everything here checks a SYNTHETIC fixture. Passing proves the generator keeps its
contracts (counts, grouped splits, rubric-only labels, RFC 5737 IPs, no payload
authorization outside B'), not that any model or label is correct in production.
Negative tests corrupt a copy of the data and assert the lint catches it, so the
lint itself is tested and not only the happy path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import data.generator_v2 as gv2
from data.generator_v2 import (
    ARCH, ARCHETYPES, SLANG, SPLITS, TARGETS, WRAPPER_FAMILIES, CohortGenerator, GeneratorError, _dump,
    generate, group_components, lint_cases, load_seed_catalog, non_rfc5737_ips, validate_archetypes,
    verify_manifest, write_dataset,
)
from data.rubric import Rubric

RUBRIC = Rubric.load()


@pytest.fixture(scope="module")
def cases():
    return generate(42)


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("cohort_v2")
    write_dataset(path, 42)
    return path


def _by(cases, **kw):
    return [c for c in cases if all(c[k] == v for k, v in kw.items())]


def _mutated(cases, case_id, **changes):
    out = copy.deepcopy(cases)
    next(c for c in out if c["case_id"] == case_id).update(changes)
    return out


# ------------------------------------------------------------------ plan and counts
def test_cohort_counts_match_d7(cases):
    assert TARGETS == {"A": 200, "B": 125, "B_prime": 60, "C": 100, "D": 75}
    for cohort, n in TARGETS.items():
        assert len(_by(cases, cohort=cohort)) == n
    assert len(cases) == 560 and len({c["case_id"] for c in cases}) == 560


def test_split_sizes_are_near_70_15_15(cases):
    for split, low, high in (("train", 0.68, 0.72), ("val", 0.13, 0.17), ("test", 0.13, 0.17)):
        assert low <= len(_by(cases, split=split)) / len(cases) <= high


def test_dataset_is_lint_clean(cases):
    assert lint_cases(cases) == []


@pytest.mark.parametrize("seed", [1, 7, 2026])
def test_other_seeds_are_also_lint_clean(seed):
    # Coverage is built in (A_CORE per split), so any seed must satisfy it, not only 42.
    assert lint_cases(generate(seed)) == []


# ------------------------------------------------------------------ determinism
def test_same_seed_is_byte_identical_and_other_seed_differs(cases):
    assert _dump(generate(42)) == _dump(cases)
    assert _dump(generate(43)) != _dump(cases)


def test_output_is_independent_of_pythonhashseed(cases):
    code = ("import hashlib; from data.generator_v2 import generate,_dump; "
            "print(hashlib.sha256(_dump(generate(42)).encode()).hexdigest())")
    digests = set()
    for hash_seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             cwd=Path(__file__).resolve().parent.parent, check=True)
        digests.add(res.stdout.strip())
    assert digests == {hashlib.sha256(_dump(cases).encode()).hexdigest()}


# ------------------------------------------------------------------ leak lint: positive and negative
def test_no_pair_template_wrapper_or_slang_crosses_splits(cases):
    for key in ("pair_id", "template_family", "wrapper_family", "slang_term"):
        seen: dict[str, set[str]] = {}
        for c in cases:
            if c[key] not in (None, "none"):
                seen.setdefault(c[key], set()).add(c["split"])
        assert seen and all(len(v) == 1 for v in seen.values()), key
    for gid, members in group_components(cases).items():
        assert len({m["split"] for m in members}) == 1, gid


def test_lint_detects_each_kind_of_split_leak(cases):
    pair_child = next(c for c in cases if c["cohort"] == "B")
    other = next(s for s in SPLITS if s != pair_child["split"])
    assert any("pair_id" in p for p in lint_cases(_mutated(cases, pair_child["case_id"], split=other)))
    tmpl = next(c for c in cases if c["cohort"] == "C")
    other = next(s for s in SPLITS if s != tmpl["split"])
    assert any("template family" in p for p in lint_cases(_mutated(cases, tmpl["case_id"], split=other)))
    wrapped = next(c for c in cases if c["wrapper_family"] == "CR")
    other = next(s for s in SPLITS if s != wrapped["split"])
    problems = lint_cases(_mutated(cases, wrapped["case_id"], split=other))
    assert any("wrapper family" in p for p in problems)
    slang = next(c for c in cases if c["slang_term"] and c["split"] == "test")
    problems = lint_cases(_mutated(cases, slang["case_id"], split="train"))
    assert any("slang term" in p for p in problems)


def test_slang_term_text_in_wrong_split_is_detected(cases):
    victim = next(c for c in cases if c["cohort"] == "A" and c["split"] == "train")
    test_term = SLANG["outage"]["test"][0][0]
    out = copy.deepcopy(cases)
    next(c for c in out if c["case_id"] == victim["case_id"])["event"]["raw"] += f" # {test_term}"
    assert any("leak: slang term" in p for p in lint_cases(out))


def test_whole_wrapper_families_are_held_out(cases):
    fams = {w.name: w.split for w in WRAPPER_FAMILIES}
    assert {n for n, s in fams.items() if s == "test"} >= {"CR", "CHAOS", "DRILL"}
    for name, split in fams.items():
        used = {c["split"] for c in cases if c["wrapper_family"] == name}
        assert used == {split}, name        # present, and only in its own split
    train_fams = {c["wrapper_family"] for c in _by(cases, split="train")} - {"none"}
    assert train_fams.isdisjoint({"CR", "CHAOS", "DRILL", "PATCH"})


def test_some_slang_terms_are_held_out_of_train(cases):
    used = {s: {c["slang_term"] for c in cases if c["split"] == s and c["slang_term"]} for s in SPLITS}
    assert used["test"] and used["val"] and used["train"]
    assert used["test"].isdisjoint(used["train"]) and used["val"].isdisjoint(used["train"])
    assert used["test"].isdisjoint(used["val"])


def test_every_split_has_all_event_types_and_primitive_values(cases):
    for split in SPLITS:
        gold = [c for c in _by(cases, split=split) if c["expected"]]
        assert {c["expected"]["choice"] for c in gold} == set(RUBRIC.event_types)
        assert {c["expected"]["noul"] for c in gold} == {True, False}
        assert {c["expected"]["score"] for c in gold} == {"P1", "P2", "P3", "P4"}


def test_lint_detects_missing_coverage(cases):
    out = [c for c in cases if not (c["split"] == "test" and c["expected"] and c["expected"]["score"] == "P1")]
    assert any("lacks some of P1..P4" in p for p in lint_cases(out))
    out = [c for c in cases if not (c["split"] == "val" and c["expected"] and c["expected"]["choice"] == "telemetry")]
    assert any("lacks event types" in p for p in lint_cases(out))
    out = [c for c in cases if not (c["split"] == "val" and c["expected"] and c["expected"]["noul"])]
    assert any("page_now" in p for p in lint_cases(out))


def test_manifest_hashes_match_files(out_dir):
    assert verify_manifest(out_dir) == []
    manifest = json.loads((out_dir / "manifest.json").read_text())
    for name, meta in manifest["files"].items():
        assert hashlib.sha256((out_dir / name).read_bytes()).hexdigest() == meta["sha256"]


def test_verify_manifest_detects_tampering(out_dir, tmp_path):
    for name in (*(f"{s}.jsonl" for s in SPLITS), "manifest.json"):
        (tmp_path / name).write_bytes((out_dir / name).read_bytes())
    assert verify_manifest(tmp_path) == []
    with open(tmp_path / "val.jsonl", "a") as handle:
        handle.write("\n")
    assert any("val.jsonl" in p and "sha256" in p for p in verify_manifest(tmp_path))
    (tmp_path / "test.jsonl").unlink()
    assert any("missing" in p for p in verify_manifest(tmp_path))
    (tmp_path / "manifest.json").write_text("{not json")
    assert any("manifest unreadable" in p for p in verify_manifest(tmp_path))


def test_files_on_disk_equal_in_memory_dataset(out_dir, cases):
    for split in SPLITS:
        assert (out_dir / f"{split}.jsonl").read_text() == _dump(_by(cases, split=split))


def test_only_rfc5737_ips_appear(cases):
    for c in cases:
        for text in gv2._strings([c["event"], c["context"]]):
            assert non_rfc5737_ips(text) == []
    assert non_rfc5737_ips("from 8.8.8.8 port 22") == ["8.8.8.8"]
    assert non_rfc5737_ips("from 198.51.100.7 port 22") == []
    assert non_rfc5737_ips("version 2.6.18.4.9 and 300.1.1.1") == []
    out = copy.deepcopy(cases)
    out[0]["event"]["raw"] += " peer 8.8.4.4"
    assert any("non-RFC5737 IP 8.8.4.4" in p for p in lint_cases(out))


# ------------------------------------------------------------------ labels come only from the rubric
def test_every_label_rederives_from_the_rubric(cases):
    # lint_cases re-runs Rubric.label on the stored event/context/evidence and compares; tamper one label.
    gold = next(c for c in cases if c["expected"])
    out = _mutated(cases, gold["case_id"], label={**gold["label"], "priority": "P1" if gold["label"]["priority"] != "P1" else "P4"})
    assert any("label_matches_rubric" in p for p in lint_cases(out))
    assert {c["label"]["rubric_version"] for c in cases if c["label"]} == {"2.4.0"}


def test_expected_fields_are_the_three_primitives(cases):
    for c in cases:
        if c["expected"]:
            assert c["expected"] == {"choice": c["label"]["event_type"], "noul": c["label"]["page_now"],
                                     "score": c["label"]["priority"]}
            assert c["questions"] == ["event_type", "page_now", "priority"]


def test_service_outage_route_exists_in_the_rubric_event_types():
    # D2: the sixth route. In rubric 2.x it is the event type 'service_degradation'.
    assert "service_degradation" in RUBRIC.event_types and len(RUBRIC.event_types) == 6


def test_cohort_d_is_never_gold(cases):
    d = _by(cases, cohort="D")
    assert len(d) == 75
    for c in d:
        assert c["label"] is None and c["expected"] is None and c["evidence"] is None
        assert c["label_status"] == "needs_adjudication"
        assert c["adjudication"]["status"] == "needs_adjudication" and c["adjudication"]["reviews"] == []
    assert all(c["label_status"] == "rubric_derived" for c in cases if c["cohort"] != "D")
    bad = _mutated(cases, d[0]["case_id"], expected={"choice": "telemetry", "noul": False, "score": "P4"})
    assert any("cohort D must stay unlabeled" in p for p in lint_cases(bad))


# ------------------------------------------------------------------ cohort B and B'
def test_b_children_pair_with_an_a_parent_in_the_same_split(cases):
    by_id = {c["case_id"]: c for c in cases}
    children = _by(cases, cohort="B")
    assert len(children) == 125
    for child in children:
        parent = by_id[child["parent_case_id"]]
        assert parent["cohort"] == "A" and parent["split"] == child["split"] and parent["pair_id"] == child["pair_id"]
        assert parent["event"] == child["event"]            # minimal pair: only the context differs
        assert parent["context"] != child["context"]
        assert parent["label"]["page_now"] is True and parent["context"]["active_changes"] == []


def test_b_pairs_flip_or_preserve_through_context_only(cases):
    by_id = {c["case_id"]: c for c in cases}
    kinds = {"label_flip": 0, "label_preserved": 0}
    for child in _by(cases, cohort="B"):
        parent = by_id[child["parent_case_id"]]
        kinds[child["pair_relation"]] += 1
        if child["pair_relation"] == "label_flip":
            assert child["label"]["handling"] == "explained_by_change" and child["expected"]["noul"] is False
            assert child["label"]["priority"] == parent["label"]["priority"]       # suppression keeps priority
        else:
            assert child["label"]["page_now"] is True
            assert child["expected"] == parent["expected"]
    assert kinds["label_flip"] == 63 and kinds["label_preserved"] == 62


def test_authorization_comes_only_from_context_in_cohort_b(cases):
    for c in _by(cases, cohort="B"):
        text = c["event"]["raw"] + " ".join(c["event"].get("window", []))
        assert not gv2.CLAIM_RE.search(text)
        assert c["context"]["active_changes"]


def test_b_prime_spoofs_keep_escalation_and_claims_live_in_the_payload(cases):
    by_id = {c["case_id"]: c for c in cases}
    spoofs = _by(cases, cohort="B_prime")
    assert len(spoofs) == 60
    assert {c["spoof_kind"] for c in spoofs} == {"no_record", "other_host", "expired", "unknown_principal"}
    for c in spoofs:
        parent = by_id[c["parent_case_id"]]
        assert gv2.CLAIM_RE.search(c["event"]["raw"])
        assert c["wrapper_family"] != "none"
        assert gv2.WRAPPER_BY_NAME[c["wrapper_family"]].id_format.split("{")[0] in c["event"]["raw"]
        assert c["expected"]["noul"] is True and c["expected"] == parent["expected"]
        assert c["label"]["handling"] == "new"
        assert all(rule != "expected_activity" for rule, _ in c["label"]["applied_rules"])
        for change in c["context"]["active_changes"]:       # a contradicting record never matches host+window
            assert change["hosts"] != [c["event"]["host"]] or change["end"] < c["event"]["ts"]


def test_authorization_claims_outside_b_prime_are_detected(cases):
    victim = next(c for c in cases if c["cohort"] == "A")
    out = copy.deepcopy(cases)
    next(c for c in out if c["case_id"] == victim["case_id"])["event"]["raw"] += " # authorized drill, do not page SOC"
    problems = lint_cases(out)
    assert any("payload authorization claim outside cohort B_prime" in p for p in problems)
    assert any("event text states the answer" in p for p in problems)   # rubric leak lint also fires


# ------------------------------------------------------------------ provenance and labelling of data
def test_each_case_records_seed_template_and_technique_and_synthetic_kind(cases):
    catalog = load_seed_catalog()
    for c in cases:
        assert c["dataset_kind"] == "synthetic_generated" and "SYNTHETIC" in c["synthetic_notice"]
        assert c["seed_source"] in {"loghub", "atomic-red-team", "generator_authored"}
        assert c["template_id"] == c["template_family"] and c["template_id"] in catalog
        assert catalog[c["template_id"]]["source"] == c["seed_source"]
        assert "attack_technique" in c
        assert c["provenance"]["seed"] == 42 and c["provenance"]["rubric_version"] == "2.4.0"
    art = [c for c in cases if c["seed_source"] == "atomic-red-team"]
    assert art and all(c["attack_technique"].startswith("T1") for c in art)
    assert all(c["attack_technique"] == "" for c in cases if c["seed_source"] != "atomic-red-team")


def test_manifest_content(out_dir):
    m = json.loads((out_dir / "manifest.json").read_text())
    assert m["dataset_kind"] == "synthetic_generated" and m["real_data"] is False
    assert m["seed"] == 42 and m["rubric_version"] == "2.4.0" and m["generator_version"] == gv2.GENERATOR_VERSION
    assert m["rubric_file_sha256"] == hashlib.sha256(gv2.DEFAULT_RUBRIC.read_bytes()).hexdigest()
    assert m["seed_registry"]["file_sha256"] == hashlib.sha256(gv2.DEFAULT_REGISTRY.read_bytes()).hexdigest()
    assert m["loghub_citation_required"] is True
    for needle in ("github.com/logpai/loghub", "ISSRE", "ISSTA", "LOGHUB_LICENSE"):
        assert needle in m["loghub_citation_note"]
    assert m["counts"]["total"] == 560 and m["counts"]["needs_adjudication"] == 75
    assert sum(m["counts"]["by_split"].values()) == 560
    assert sum(g["n_cases"] for g in m["groups"].values()) == 560
    assert set(m["split_policy"]["wrapper_family_split"]) == {w.name for w in WRAPPER_FAMILIES}
    assert m["seed_sources_used"]["generator_authored"] > 0       # authored seeds are disclosed, not hidden
    assert "created_at" not in m and "hostname" not in m      # reproducible and no personal telemetry
    assert "leave-one-source-out splits" in m["not_implemented"]


def test_manifest_group_ids_match_split_files(out_dir):
    m = json.loads((out_dir / "manifest.json").read_text())
    rows = {s: [json.loads(x) for x in (out_dir / f"{s}.jsonl").read_text().splitlines()] for s in SPLITS}
    pairs = {s: {r["pair_id"] for r in rs} for s, rs in rows.items()}
    for gid, g in m["groups"].items():
        assert set(g["pair_ids"]) <= pairs[g["split"]], gid


# ------------------------------------------------------------------ text realism and answer-leak guards
def test_event_text_does_not_state_the_answer(cases):
    for c in cases:
        text = "\n".join([c["event"]["raw"], *c["event"].get("window", [])])
        if c["cohort"] != "B_prime":
            assert RUBRIC.leak_violations(text, c["cohort"]) == [], c["case_id"]
        assert "<*>" not in text and "#{" not in text, c["case_id"]


def test_slang_lexicon_is_clean_and_versioned():
    assert gv2.LEXICON_VERSION
    for topic, by_split in SLANG.items():
        for split in SPLITS:
            for term, phrase in by_split[split]:
                assert term.lower() in phrase.lower(), (topic, term)
                assert RUBRIC.leak_violations(phrase.format(host="h-1"), "C") == []


# ------------------------------------------------------------------ static plan and error handling
def test_static_plan_is_valid():
    validate_archetypes(load_seed_catalog())
    owner = {}
    for a in ARCHETYPES:
        for t in a.templates:
            assert t not in owner, t
            owner[t] = a.id
        assert a.templates and a.variants
    assert set(a.event_type for a in ARCHETYPES) == set(RUBRIC.event_types)


def test_seed_in_two_pools_is_rejected(monkeypatch):
    catalog = load_seed_catalog()
    a, b = ARCHETYPES[0], ARCHETYPES[1]
    bad = tuple(ARCHETYPES[:1]) + (gv2.dataclasses.replace(b, templates=b.templates + (a.templates[0],)),) + tuple(ARCHETYPES[2:])
    monkeypatch.setattr(gv2, "ARCHETYPES", bad)
    with pytest.raises(GeneratorError, match="exactly one pool"):
        validate_archetypes(catalog)


def test_missing_seed_and_small_pool_are_rejected(monkeypatch):
    catalog = load_seed_catalog()
    a = ARCHETYPES[0]
    monkeypatch.setattr(gv2, "ARCHETYPES", (gv2.dataclasses.replace(a, templates=a.templates[:2]),) + tuple(ARCHETYPES[1:]))
    with pytest.raises(GeneratorError, match="needs >= 3 templates"):
        validate_archetypes(catalog)
    monkeypatch.setattr(gv2, "ARCHETYPES", (gv2.dataclasses.replace(a, templates=a.templates[:-1] + ("Nope-E1",)),) + tuple(ARCHETYPES[1:]))
    with pytest.raises(GeneratorError, match="not in registry"):
        validate_archetypes(catalog)


def test_missing_or_malformed_registry_fails_loudly(tmp_path):
    with pytest.raises(GeneratorError, match="not found"):
        load_seed_catalog(tmp_path / "nope.jsonl")
    bad = tmp_path / "registry.jsonl"
    bad.write_text("{not json}\n")
    with pytest.raises(GeneratorError, match="bad registry record"):
        load_seed_catalog(bad)
    bad.write_text('{"template_id": "x"}\n')
    with pytest.raises(GeneratorError, match="bad registry record"):
        load_seed_catalog(bad)
    rec = json.dumps({"source": "loghub", "template_id": "X-E1", "template": "a"})
    bad.write_text(rec + "\n" + rec + "\n")
    with pytest.raises(GeneratorError, match="duplicate template_id"):
        load_seed_catalog(bad)


def test_unresolved_placeholder_is_an_error_not_a_silent_default(monkeypatch):
    # AUTH-RL-1 needs {n}; a variant without 'n' must fail loudly instead of printing a made-up number.
    arch = ARCH["replication_lag"]
    v = gv2.dataclasses.replace(arch.variants[0], nums=())
    monkeypatch.setitem(gv2.ARCH, "replication_lag", gv2.dataclasses.replace(arch, variants=(v, arch.variants[1])))
    gen = CohortGenerator(42)
    with pytest.raises(GeneratorError, match="unresolved placeholder"):
        gen._build_base("replication_lag", "std", "train", "t", tid="AUTH-RL-1")


def test_art_seed_with_undeclared_argument_fails(monkeypatch):
    import random
    rec = {"template_id": "T0-x", "template": "echo #{missing}", "input_arguments": {}}
    with pytest.raises(GeneratorError, match="undeclared argument"):
        CohortGenerator._render_art(rec, random.Random(0))


def test_rubric_conflicts_in_the_plan_raise(monkeypatch):
    # An archetype whose variant claims a critical threat but impact < moderate is rejected by the rubric
    # itself; the generator surfaces the error rather than patching the label.
    arch = ARCH["replication_lag"]
    bad = gv2.dataclasses.replace(arch.variants[0], threatens_critical=True, criticality="high")
    monkeypatch.setitem(gv2.ARCH, "replication_lag", gv2.dataclasses.replace(arch, variants=(bad, arch.variants[1])))
    with pytest.raises(Exception, match="impact < moderate"):
        CohortGenerator(42).build()


def test_a_non_paging_b_parent_is_rejected(monkeypatch):
    arch = ARCH["db_failover"]
    quiet = gv2.dataclasses.replace(arch.variants[0], urgency="deferred", actionable=False)
    monkeypatch.setitem(gv2.ARCH, "db_failover", gv2.dataclasses.replace(arch, variants=(quiet,)))
    with pytest.raises(GeneratorError, match="must page"):
        CohortGenerator(42).build()


def test_build_twice_is_rejected():
    gen = CohortGenerator(42)
    gen.build()
    with pytest.raises(GeneratorError, match="already ran"):
        gen.build()


def test_split_count_helpers():
    assert gv2._counts(63) == (45, 9, 9) and gv2._counts(75) == (53, 11, 11)
    labels = gv2._spaced_splits(77)
    assert labels.count("val") == labels.count("test") == 12 and len(labels) == 77
    with pytest.raises(GeneratorError):
        gv2._spaced_splits(10, (1, 1, 1))


# ------------------------------------------------------------------ CLI
def test_cli_writes_and_verifies(tmp_path, capsys):
    assert gv2.main(["--output", str(tmp_path / "o"), "--seed", "42"]) == 0
    assert "SYNTHETIC" in capsys.readouterr().out
    assert verify_manifest(tmp_path / "o") == []


def test_cli_reports_generator_errors(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise GeneratorError("boom")
    monkeypatch.setattr(gv2, "write_dataset", boom)
    assert gv2.main(["--output", str(tmp_path)]) == 2
    assert "boom" in capsys.readouterr().err


def test_cli_reports_verification_failures(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gv2, "verify_manifest", lambda p: ["synthetic problem"])
    assert gv2.main(["--output", str(tmp_path / "o")]) == 1
    assert "synthetic problem" in capsys.readouterr().err
