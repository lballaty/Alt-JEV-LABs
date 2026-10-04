"""Loader, manifest tamper detection and task mapping for evaluation/v2_data.py."""

import hashlib
import json
from pathlib import Path

import pytest

from data.rubric import PRIORITIES
from evaluation import v2_data as d
from v2_fixtures import mk_case


def rewrite_split(directory: Path, split: str, mutate) -> None:
    """Change cases in a split and re-sign the manifest entry, simulating a *consistent* but bad dataset."""
    path = directory / f"{split}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        mutate(row)
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    path.write_text(body)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["files"][f"{split}.jsonl"].update(sha256=hashlib.sha256(body.encode()).hexdigest(),
                                                bytes=len(body.encode()), cases=len(rows))
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def edit_manifest(directory: Path, **changes) -> None:
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(changes)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


# ----------------------------------------------------------------------------- loading
def test_loads_val_and_test_only_by_default(v2_dir):
    ds = d.load_v2_dataset(v2_dir)
    assert set(ds.cases) == {"val", "test"}
    assert len(ds.test) == 83 and len(ds.val) == 83
    assert {c["split"] for c in ds.test} == {"test"} and {c["cohort"] for c in ds.test} == set(d.COHORTS)
    with pytest.raises(KeyError, match="not loaded"):
        ds.split("train")
    assert ds.dataset_kind == "synthetic_generated" and ds.uses_loghub
    assert ds.manifest_sha256 == hashlib.sha256((v2_dir / "manifest.json").read_bytes()).hexdigest()
    assert len(ds.by_id) == 166 and ds.group_of_pair


def test_loads_train_only_on_request(v2_dir):
    ds = d.load_v2_dataset(v2_dir, splits=("train",))
    assert set(ds.cases) == {"train"} and len(ds.split("train")) == 394
    with pytest.raises(ValueError, match="unknown splits"):
        d.load_v2_dataset(v2_dir, splits=("dev",))


# ----------------------------------------------------------------------------- tamper detection
def test_edited_split_file_is_rejected(v2_dir):
    with (v2_dir / "test.jsonl").open("a") as f:
        f.write("\n")
    with pytest.raises(d.DatasetIntegrityError, match="sha256 does not match manifest"):
        d.load_v2_dataset(v2_dir)


def test_flipped_label_is_rejected_even_if_hash_is_resigned(v2_dir):
    def flip(row):
        if row["expected"] and row["case_id"].startswith("A-"):
            row["expected"]["noul"] = not row["expected"]["noul"]
    rewrite_split(v2_dir, "test", flip)                   # manifest re-signed: hashes pass, the loader's own check must catch it
    with pytest.raises(d.DatasetIntegrityError, match="expected answers do not match the stored label"):
        d.load_v2_dataset(v2_dir)


def test_missing_file_and_missing_manifest(v2_dir):
    (v2_dir / "val.jsonl").unlink()
    with pytest.raises(d.DatasetIntegrityError, match="listed in manifest but missing"):
        d.load_v2_dataset(v2_dir)
    (v2_dir / "manifest.json").unlink()
    with pytest.raises(d.DatasetIntegrityError, match="manifest unreadable"):
        d.load_v2_dataset(v2_dir)


def test_manifest_hash_edit_is_rejected(v2_dir):
    manifest = json.loads((v2_dir / "manifest.json").read_text())
    manifest["files"]["test.jsonl"]["sha256"] = "0" * 64
    (v2_dir / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(d.DatasetIntegrityError, match="test.jsonl: sha256"):
        d.load_v2_dataset(v2_dir)


def test_rubric_hash_drift_is_rejected_unless_allowed(v2_dir):
    edit_manifest(v2_dir, rubric_file_sha256="f" * 64)
    with pytest.raises(d.DatasetIntegrityError, match="rubric file hash differs"):
        d.load_v2_dataset(v2_dir)
    assert d.load_v2_dataset(v2_dir, allow_rubric_drift=True).manifest["rubric_file_sha256"] == "f" * 64


def test_real_data_flag_and_unknown_kind_rejected(v2_dir):
    edit_manifest(v2_dir, real_data=True)
    with pytest.raises(d.DatasetIntegrityError, match="real_data"):
        d.load_v2_dataset(v2_dir)
    edit_manifest(v2_dir, real_data=False, dataset_kind="real_deidentified")
    with pytest.raises(d.DatasetIntegrityError, match="unsupported dataset_kind"):
        d.load_v2_dataset(v2_dir)


def test_questions_contract_is_enforced(v2_dir):
    rewrite_split(v2_dir, "test", lambda r: r.__setitem__("questions", ["event_type", "page_now"]))
    with pytest.raises(d.DatasetIntegrityError, match="questions"):
        d.load_v2_dataset(v2_dir)


def test_row_in_wrong_split_file_rejected(v2_dir):
    done = []

    def relabel(row):
        if not done:
            row["split"] = "val"
            done.append(1)
    rewrite_split(v2_dir, "test", relabel)
    with pytest.raises(d.DatasetIntegrityError):
        d.load_v2_dataset(v2_dir)


def test_dataset_label_for_unknown_kind_raises():
    assert d.dataset_label("synthetic_generated") == "SYNTHETIC (generated), not real data"
    with pytest.raises(d.DatasetIntegrityError):
        d.dataset_label("mystery")


# ----------------------------------------------------------------------------- mapping
def test_gold_and_task_tables():
    case = mk_case("A1", "A", "telemetry", False, "P4")
    assert d.gold(case) == {"event_type": "telemetry", "page_now": False, "priority": "P4"}
    assert d.gold(mk_case("D1", "D", None, None, None)) is None
    assert d.TASKS == ("event_type", "page_now", "priority")
    assert d.TASK_KIND == {"event_type": "choice", "page_now": "noul", "priority": "score"}
    assert set(d.PRIORITY_ANCHOR) == set(PRIORITIES)
    assert [d.level_from_score(a) for a in d.PRIORITY_ANCHOR.values()] == list(d.PRIORITY_ANCHOR)   # round trip


def test_event_types_come_from_frozen_rubric():
    types = d.event_types()
    assert len(types) == 6 and "service_degradation" in types and "telemetry" in types


def test_to_decision_cases_withholds_targets_and_maps_tasks(v2_dir):
    ds = d.load_v2_dataset(v2_dir)
    case = next(c for c in ds.test if c["cohort"] == "A")
    blind = d.to_decision_cases(case, with_target=False)
    assert set(blind) == set(d.TASKS) and all(dc.target is None for dc in blind.values())
    assert blind["event_type"].kind == "choice" and blind["event_type"].options == d.event_types()
    assert blind["page_now"].kind == "noul" and blind["priority"].kind == "score"
    assert blind["page_now"].id == f"{case['case_id']}::page_now" and blind["page_now"].pair_id == case["pair_id"]
    assert blind["page_now"].state == blind["priority"].state == d.render_state(case)
    fit = d.to_decision_cases(case, with_target=True)
    assert fit["event_type"].target == case["expected"]["choice"]
    assert fit["page_now"].target is case["expected"]["noul"]
    assert fit["priority"].target == d.PRIORITY_ANCHOR[case["expected"]["score"]]
    spoof = next(c for c in ds.test if c["cohort"] == "B_prime")
    assert d.to_decision_cases(spoof, with_target=False)["page_now"].adversarial is True
    ungraded = next(c for c in ds.test if c["cohort"] == "D")
    with pytest.raises(d.DatasetIntegrityError, match="ungraded"):
        d.to_decision_cases(ungraded, with_target=True)
    assert d.to_decision_cases(ungraded, with_target=False)["priority"].target is None


def test_rendered_state_is_an_allow_list(v2_dir):
    """No label, evidence or generator metadata reaches the model text."""
    ds = d.load_v2_dataset(v2_dir)
    types = d.event_types()
    for case in ds.test + ds.val:
        text = d.render_state(case, include_signal=False)
        assert case["event"]["raw"] in text and "CONTEXT" in text
        for forbidden in (*types, "rubric_derived", "needs_adjudication", "label_flip", "label_preserved",
                          "synthetic_notice", '"expected"', case["case_id"], case["pair_id"]):
            assert forbidden not in text, (case["case_id"], forbidden)
        if case["label"]:
            assert case["label"]["immediate_action"] is None or case["label"]["immediate_action"] not in text
        if case["spoof_kind"]:
            assert f'"{case["spoof_kind"]}"' not in text
    sample = ds.test[0]
    assert '"signal"' in d.render_state(sample, include_signal=True)
    assert '"signal"' not in d.render_state(sample, include_signal=False)
    assert d.render_state(sample) == d.render_state(sample)         # deterministic


def test_loader_defence_in_depth_when_the_generator_lint_is_bypassed(v2_dir, monkeypatch):
    """The loader re-checks the contract itself; simulate a generator lint that let bad rows through."""
    monkeypatch.setattr(d, "verify_manifest", lambda directory: [])

    rewrite_split(v2_dir, "test", lambda r: r.__setitem__("cohort", "Z"))
    with pytest.raises(d.DatasetIntegrityError, match="unknown cohort"):
        d.load_v2_dataset(v2_dir)

    rewrite_split(v2_dir, "test", lambda r: r.__setitem__("cohort", "A"))
    rewrite_split(v2_dir, "test", lambda r: r.__setitem__("case_id", "A-0001"))
    with pytest.raises(d.DatasetIntegrityError, match="duplicate case_id"):
        d.load_v2_dataset(v2_dir)


def test_file_changed_between_verification_and_read_is_caught(v2_dir, monkeypatch):
    def verify_then_tamper(directory):
        with (directory / "test.jsonl").open("a") as f:
            f.write("\n")
        return []                                   # verification "passed", then the file changed
    monkeypatch.setattr(d, "verify_manifest", verify_then_tamper)
    with pytest.raises(d.DatasetIntegrityError, match="changed after verification"):
        d.load_v2_dataset(v2_dir)


def test_split_field_mismatch_caught_even_without_generator_lint(v2_dir, monkeypatch):
    monkeypatch.setattr(d, "verify_manifest", lambda directory: [])
    rewrite_split(v2_dir, "test", lambda r: r.__setitem__("split", "val"))
    with pytest.raises(d.DatasetIntegrityError, match="found in test.jsonl"):
        d.load_v2_dataset(v2_dir)


def test_loader_rejects_graded_cohort_d(v2_dir, monkeypatch):
    monkeypatch.setattr(d, "verify_manifest", lambda directory: [])
    state = {"done": False}

    def grade_d(row):
        if row["cohort"] == "D" and not state["done"]:
            state["done"] = True
            row["label"] = {"event_type": "telemetry", "page_now": False, "priority": "P4"}
    rewrite_split(v2_dir, "test", grade_d)
    with pytest.raises(d.DatasetIntegrityError, match="cohort D must be ungraded"):
        d.load_v2_dataset(v2_dir)


def test_expected_without_label_is_rejected():
    with pytest.raises(d.DatasetIntegrityError, match="do not match"):
        d._check_expected_matches_label({"case_id": "X", "label": None,
                                         "expected": {"choice": "a", "noul": True, "score": "P1"}})
    d._check_expected_matches_label({"case_id": "X", "label": None, "expected": None})       # ungraded is fine
