"""Runner plumbing with stub candidates defined in tests/v2_fixtures.py (test doubles, not models).

Nothing here measures a model. The assertions check accounting: statuses, withheld targets, timing,
validation-only calibration and that the lexical adapter can be driven through the v2 mapping.
"""

import pytest

from evaluation import v2_runner as r
from evaluation.v2_data import TASKS, load_v2_dataset, to_decision_cases
from evaluation.v2_metrics import calibration_summary
from models.base import ModelUnavailable
from training.calibrate import fit_temperature
from v2_fixtures import StubAlwaysPage, StubDeclared, StubFailures, StubHardLabel, StubKeyword


@pytest.fixture
def ds(v2_dir):
    return load_v2_dataset(v2_dir)


class FakeClock:
    """Deterministic clock: every call advances 1 ms, so each timed call measures exactly 1 ms."""

    def __init__(self):
        self.t = 0

    def __call__(self):
        self.t += 1_000_000
        return self.t


def test_every_call_gets_an_outcome_and_targets_are_withheld(ds):
    stub = StubKeyword()
    run = r.run_candidate(r.CandidateSpec("stub", "raw", stub), ds)
    assert run.status == "unmeasured_timing" and run.timing["status"] == "not run (iterations=0)"
    assert len(run.test) == 83 * 3 and len(run.val) == 83 * 3
    assert {k[1] for k in run.test} == set(TASKS)
    assert all(o.status == "ok" for o in run.test.values())
    assert stub.seen_targets and all(t is None for t in stub.seen_targets)      # the adapter never sees gold
    assert run.test[(ds.test[0]["case_id"], "page_now")].probability_source == "model"
    again = r.run_candidate(r.CandidateSpec("stub", "raw", StubKeyword()), ds)
    assert again.test == run.test                                               # deterministic


def test_outcome_conversion_rules(ds):
    run = r.run_candidate(r.CandidateSpec("stub", "raw", StubKeyword()), ds)
    case = next(c for c in ds.test if "Failed password" in c["event"]["raw"] + " ".join(c["event"].get("window", [])))
    cid = case["case_id"]
    assert run.test[(cid, "page_now")].value is True                            # 0.9 >= 0.5 threshold
    assert run.test[(cid, "priority")].value == "P1" and run.test[(cid, "priority")].raw_score == 90.0
    assert run.test[(cid, "event_type")].value == "security_event"              # stub picks options[0] when risky
    calm = next(c for c in ds.test if "Failed password" not in c["event"]["raw"] + " ".join(c["event"].get("window", []))
                and "sudoers" not in " ".join(c["event"].get("window", [])))
    assert run.test[(calm["case_id"], "page_now")].value is False               # 0.2 < 0.5
    assert run.test[(calm["case_id"], "priority")].value == "P4"                # 10.0 falls in the lowest bin


def test_error_statuses_are_kept_separate(ds):
    run = r.run_candidate(r.CandidateSpec("fail", "raw", StubFailures()), ds)
    statuses = {t: {o.status for k, o in run.test.items() if k[1] == t} for t in TASKS}
    assert statuses == {"event_type": {"ok"}, "page_now": {"unsupported"}, "priority": {"exception"}}
    assert any("stub backend failure" in e for e in (o.error or "" for o in run.test.values()))
    assert run.first_errors and len(run.first_errors) <= 3
    flaky = r.run_candidate(r.CandidateSpec("flaky", "raw", StubKeyword(fail_priority_every=7)), ds)
    assert {o.status for o in flaky.test.values()} == {"ok", "schema_failure"}


def test_declared_unsupported_tasks_are_not_called(ds):
    stub = StubDeclared()
    run = r.run_candidate(r.CandidateSpec("declared", "raw", stub), ds)
    assert set(stub.kinds_called) == {"choice", "noul"}                         # no "score" call was made
    assert {o.status for k, o in run.test.items() if k[1] == "priority"} == {"unsupported"}
    assert "declared v2_supported_tasks" in next(o.error for k, o in run.test.items() if k[1] == "priority")


def test_unavailable_candidate_and_spec_validation(ds):
    with pytest.raises(ValueError, match="unavailable_reason"):
        r.CandidateSpec("x", "raw", None)
    with pytest.raises(ValueError, match="unknown operational keys"):
        r.CandidateSpec("x", "raw", StubKeyword(), operational={"typo": 1})
    spec = r.CandidateSpec("laya", "raw", None, unavailable_reason="needs Mac")
    run = r.run_candidate(spec, ds)
    assert run.status == "unavailable" and run.test is None and run.note == "needs Mac"
    assert spec.key == "laya/raw"


def test_timing_uses_untimed_warmup_and_cycles_answered_calls(ds):
    stub = StubKeyword()
    run = r.run_candidate(r.CandidateSpec("stub", "raw", stub), ds, iterations=7, warmup=3, clock=FakeClock())
    assert run.status == "measured" and len(run.latencies) == 7
    assert all(ms == pytest.approx(1.0) for _, ms in run.latencies)
    # 166*3 scored calls, plus warmup + timed calls on the test split only
    assert stub.calls == (83 + 83) * 3 + 3 + 7
    assert run.timing["samples"] == 7 and "perf_counter_ns" in run.timing["method"]


def test_timing_stops_on_backend_error_and_reports_partial(ds):
    class Breaks(StubKeyword):
        def evaluate(self, case):
            if self.calls >= 166 * 3 + 4:
                raise RuntimeError("backend died during timing")
            return super().evaluate(case)

    run = r.run_candidate(r.CandidateSpec("b", "raw", Breaks()), ds, iterations=10, warmup=2, clock=FakeClock())
    assert run.status == "partial" and len(run.latencies) == 2
    assert any("timing" in e and "backend died" in e for e in run.first_errors)
    with pytest.raises(ValueError):
        r.time_calls(StubKeyword(), {}, {}, -1, 0, FakeClock(), [])
    assert r.time_calls(StubKeyword(), {}, {}, 5, 0, FakeClock(), [])[1] == "not run (no answered calls to time)"


def test_calibrated_arm_is_fitted_on_validation_only(ds):
    raw = r.run_candidate(r.CandidateSpec("stub", "raw", StubKeyword()), ds)
    cal = r.fit_calibrated_arm(raw, ds)
    assert cal.spec.arm == "calibrated" and cal.calibration["fit_split"] == "val" and cal.calibration["fit_on_test"] is False
    # re-derive the fit from validation data directly: same temperature, same n
    probs, labels = [], []
    for (cid, task), out in sorted(raw.val.items()):
        case = next(c for c in ds.val if c["case_id"] == cid)
        if task == "page_now" and case["expected"]:
            probs.append(out.probability)
            labels.append(case["expected"]["noul"])
    assert cal.calibration["temperature"] == fit_temperature(probs, labels)
    assert cal.calibration["fit_n"] == len(probs)
    for key, out in raw.test.items():                                            # decisions are unchanged
        assert cal.test[key].value == out.value
    page = next(o for k, o in cal.test.items() if k[1] == "page_now")
    assert page.probability_source == "model_temperature_scaled"
    assert calibration_summary(ds.test, cal.test)["n"] > 0
    assert calibration_summary(ds.test, raw.test)["n"] > 0


def test_calibration_changes_only_probabilities_not_the_fit_when_test_changes(ds):
    """Changing test outputs must not move the fitted temperature (no test leakage into calibration)."""
    raw = r.run_candidate(r.CandidateSpec("stub", "raw", StubKeyword()), ds)
    t1 = r.fit_calibrated_arm(raw, ds).calibration["temperature"]
    raw.test = {k: (o.__class__(o.case_id, o.task, o.status, not o.value, 0.01, o.probability_source)
                    if k[1] == "page_now" else o) for k, o in raw.test.items()}
    assert r.fit_calibrated_arm(raw, ds).calibration["temperature"] == t1


def test_uncalibratable_and_unavailable_arms(ds):
    hard = r.run_candidate(r.CandidateSpec("hard", "raw", StubHardLabel()), ds)
    cal = r.fit_calibrated_arm(hard, ds)
    assert cal.status == "unavailable" and "source must be 'model'" in cal.note
    gone = r.fit_calibrated_arm(r.run_candidate(r.CandidateSpec("g", "raw", None, unavailable_reason="no"), ds), ds)
    assert gone.status == "unavailable" and "raw arm unavailable" in gone.note
    unsupported = r.run_candidate(r.CandidateSpec("f", "raw", StubFailures()), ds)
    assert r.fit_calibrated_arm(unsupported, ds).status == "unavailable"


def test_lexical_bm25_plumbing_through_the_v2_mapping(v2_dir):
    """Plumbing only: proves the existing adapter can be driven via the v2 task mapping. Not a result."""
    pytest.importorskip("rank_bm25")
    from models.lexical_bm25 import LexicalBM25
    train = load_v2_dataset(v2_dir, splits=("train",)).split("train")
    fit = [dc for c in train if c["expected"] for dc in to_decision_cases(c, with_target=True).values()]
    run = r.run_candidate(r.CandidateSpec("lexical", "raw", LexicalBM25(fit)), load_v2_dataset(v2_dir))
    assert len(run.test) == 83 * 3
    assert {o.status for o in run.test.values()} == {"ok"}
    assert {o.probability_source for k, o in run.test.items() if k[1] == "page_now"} == {"hard_label_uncalibrated"}
    assert r.fit_calibrated_arm(run, load_v2_dataset(v2_dir)).status == "unavailable"


def test_environment_has_no_personal_identifiers():
    env = r.collect_environment()
    assert {"python", "platform", "hardware", "packages", "memory_sampling"} <= set(env)
    assert "host" not in " ".join(env).lower().replace("hardware", "")
    assert "rank-bm25" in env["packages"]


def test_modelunavailable_during_call_is_unsupported_not_exception(ds):
    class Absent(StubAlwaysPage):
        def evaluate(self, case):
            raise ModelUnavailable("checkpoint missing")

    run = r.run_candidate(r.CandidateSpec("absent", "raw", Absent()), ds)
    assert {o.status for o in run.test.values()} == {"unsupported"}
