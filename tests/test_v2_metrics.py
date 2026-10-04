"""Unit tests for evaluation/v2_metrics.py. Expected values are worked out by hand in the comments."""

import pytest

from evaluation import v2_metrics as m
from evaluation.metrics import ece
from evaluation.v2_data import level_from_score
from v2_fixtures import mk_case, mk_outs, perfect_outcomes


# ----------------------------------------------------------------------------- Wilson
def test_wilson_known_values():
    # 8/10: centre = (0.8 + 1.9207/10) / 1.38415 = 0.7167, half = 0.2266 -> [0.4902, 0.9433]
    low, high = m.wilson_interval(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-3) and high == pytest.approx(0.9433, abs=1e-3)
    # 0/10 -> [0, z^2/(n+z^2)] = [0, 0.2775]; 10/10 mirrors it
    low, high = m.wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    low, high = m.wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-3) and high == pytest.approx(1.0)


def test_wilson_empty_and_invalid():
    assert m.wilson_interval(0, 0) is None
    for bad in ((-1, 5), (6, 5)):
        with pytest.raises(ValueError):
            m.wilson_interval(*bad)


def test_proportion_na_is_never_zero():
    p = m.proportion(0, 0, "unsupported")
    assert p.rate is None and p.low is None and p.na_reason == "unsupported"
    assert p.to_dict()["rate"] is None
    q = m.proportion(3, 4)
    assert q.rate == 0.75 and q.na_reason is None and q.to_dict()["ci_method"] == "wilson95"
    na = m.not_applicable("why")
    assert na.den == 0 and na.na_reason == "why"


# ----------------------------------------------------------------------------- bootstrap
def test_bootstrap_hand_values_and_determinism():
    a = {"c1": 1.0, "c2": 1.0, "c3": 0.0, "c4": 1.0}
    b = {"c1": 0.0, "c2": 1.0, "c3": 0.0, "c4": 0.0}
    cl = {k: k for k in a}
    r1 = m.paired_bootstrap_diff(a, b, cl, seed=7, n_boot=500)
    r2 = m.paired_bootstrap_diff(a, b, cl, seed=7, n_boot=500)
    assert r1 == r2                                    # same seed, same interval
    assert r1["diff"] == pytest.approx(0.5)           # (2 of 4 differ by +1) / 4
    assert r1["n"] == 4 and r1["n_clusters"] == 4 and r1["ci_low"] <= 0.5 <= r1["ci_high"]
    assert m.paired_bootstrap_diff(a, b, cl, seed=8, n_boot=500)["ci_low"] is not None


def test_bootstrap_identical_and_extreme():
    ones = {f"c{i}": 1.0 for i in range(5)}
    zeros = {f"c{i}": 0.0 for i in range(5)}
    cl = {k: k for k in ones}
    same = m.paired_bootstrap_diff(ones, ones, cl, 1, 200)
    assert same["diff"] == 0 and same["ci_low"] == 0 and same["ci_high"] == 0
    full = m.paired_bootstrap_diff(ones, zeros, cl, 1, 200)
    assert full["diff"] == 1 and full["ci_low"] == 1 and full["ci_high"] == 1


def test_bootstrap_uses_only_identical_cases_and_reports_na():
    a, b = {"x": 1.0, "y": 0.0}, {"y": 1.0, "z": 1.0}
    r = m.paired_bootstrap_diff(a, b, {}, 3, 50)
    assert r["n"] == 1 and r["diff"] == -1.0           # only "y" is common
    assert r["ci_low"] is None and "fewer than two clusters" in r["na_reason"]
    none = m.paired_bootstrap_diff({"x": 1.0}, {"z": 1.0}, {}, 3, 50)
    assert none["diff"] is None and "no identical cases" in none["na_reason"]
    for kwargs in ({"n_boot": 0}, {"confidence": 1.0}):
        with pytest.raises(ValueError):
            m.paired_bootstrap_diff(a, b, {}, 3, **({"n_boot": 10} | kwargs))


def test_bootstrap_resamples_clusters_not_cases():
    # Two clusters of two perfectly correlated cases: resampling clusters can give mean 0 or 1 only.
    a = {"a1": 1.0, "a2": 1.0, "b1": 0.0, "b2": 0.0}
    b = {k: 0.0 for k in a}
    clusters = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    r = m.paired_bootstrap_diff(a, b, clusters, seed=0, n_boot=400)
    assert r["n_clusters"] == 2 and r["diff"] == 0.5
    assert r["ci_low"] == 0.0 and r["ci_high"] == 1.0


# ----------------------------------------------------------------------------- cohort A cell
def cohort_a():
    cases = [mk_case("A1", "A", "security_event", True, "P1"),
             mk_case("A2", "A", "service_degradation", True, "P2"),
             mk_case("A3", "A", "telemetry", False, "P4"),
             mk_case("A4", "A", "routine_activity", False, "P4"),
             mk_case("A5", "A", "security_event", True, "P1")]
    outs = {}
    outs.update(mk_outs("A1", "security_event", True, "P1"))          # all right
    outs.update(mk_outs("A2", "security_event", False, "P4"))         # event wrong, page missed, priority gap 2
    outs.update(mk_outs("A3", "telemetry", True, "P3"))               # false page, priority gap 1
    outs.update(mk_outs("A4", "schema", "exc", "unsup"))              # no answers
    outs.update(mk_outs("A5", "security_event", "exc", "P1"))         # page_now backend exception on a must-page
    return cases, outs


def test_cohort_a_cells_hand_computed():
    cases, outs = cohort_a()
    cell = m.cohort_metrics(cases, outs, {c["case_id"]: c for c in cases}, "A")
    # 15 calls: ok = 11, schema 1, exception 2 (A4 page, A5 page), unsupported 1 (A4 priority)
    assert (cell["coverage"].num, cell["coverage"].den) == (11, 15)
    assert (cell["schema_failure_rate"].num, cell["schema_failure_rate"].den) == (1, 14)   # attempted = 14
    assert (cell["exception_rate"].num, cell["exception_rate"].den) == (2, 14)
    assert (cell["unsupported_rate"].num, cell["unsupported_rate"].den) == (1, 15)
    # event_type answered A1,A2,A3,A5; right A1,A3,A5
    assert (cell["event_type_accuracy"].num, cell["event_type_accuracy"].den) == (3, 4)
    # page_now answered A1,A2,A3; right A1 only
    assert (cell["page_now_accuracy"].num, cell["page_now_accuracy"].den) == (1, 3)
    # must-page gold True: A1,A2,A5. Answered A1 (hit), A2 (miss) -> 1/2; strict counts A5 as a miss -> 1/3
    assert (cell["must_page_recall"].num, cell["must_page_recall"].den) == (1, 2)
    assert (cell["must_page_recall_strict"].num, cell["must_page_recall_strict"].den) == (1, 3)
    # gold False: A3 (paged), A4 (page_now non-answer, excluded)
    assert (cell["false_page_rate"].num, cell["false_page_rate"].den) == (1, 1)
    # priority answered A1,A2,A3,A5 gaps 0,2,1,0
    assert (cell["priority_accuracy"].num, cell["priority_accuracy"].den) == (2, 4)
    assert (cell["priority_within_one"].num, cell["priority_within_one"].den) == (3, 4)
    assert cell["priority_mae_levels"]["mean"] == 0.75 and cell["priority_mae_levels"]["n"] == 4
    assert cell["per_task_status"]["priority"] == {"ok": 4, "schema_failure": 0, "exception": 0,
                                                    "unsupported": 1, "calls": 5}
    # cohort-specific cells are N/A, never 0
    assert cell["paired_inversion"].rate is None and cell["spoof_escalation_kept"].rate is None


def test_all_unsupported_task_is_na_with_reason():
    cases = [mk_case("A1", "A"), mk_case("A2", "A", "telemetry", False, "P4")]
    outs = {**mk_outs("A1", "security_event", True, "unsup"), **mk_outs("A2", "telemetry", False, "unsup")}
    cell = m.cohort_metrics(cases, outs, {c["case_id"]: c for c in cases}, "A")
    for key in ("priority_accuracy", "priority_within_one"):
        assert cell[key].rate is None
    assert "unsupported by this candidate" in cell["priority_accuracy"].na_reason
    assert cell["priority_mae_levels"]["mean"] is None and cell["priority_mae_levels"]["n"] == 0
    assert cell["event_type_accuracy"].rate == 1.0


def test_missing_outcome_raises():
    cases = [mk_case("A1", "A")]
    with pytest.raises(ValueError, match="missing outcome"):
        m.cohort_metrics(cases, {}, {"A1": cases[0]}, "A")


def test_outcome_validation():
    with pytest.raises(ValueError):
        m.Outcome("c", "page_now", "weird")
    with pytest.raises(ValueError):
        m.Outcome("c", "colour", "ok")
    assert m.Outcome("c", "page_now", "ok", True, 0.7, "model").to_dict()["probability"] == 0.7


# ----------------------------------------------------------------------------- B pairs and B'
def test_paired_inversion_hand_computed():
    cases = [mk_case("A1", "A", page=True), mk_case("A2", "A", page=False, event_type="telemetry", prio="P4"),
             mk_case("A3", "A", page=True), mk_case("A4", "A", page=True),
             mk_case("B1", "B", page=False, parent="A1", relation="label_flip"),
             mk_case("B2", "B", page=True, parent="A1", relation="label_preserved"),
             mk_case("B3", "B", page=False, parent="A3", relation="label_flip"),
             mk_case("B4", "B", page=False, parent="A4", relation="label_flip")]
    outs = {}
    outs.update(mk_outs("A1", "security_event", True, "P1"))
    outs.update(mk_outs("A2", "telemetry", False, "P4"))
    outs.update(mk_outs("A3", "security_event", True, "P1"))
    outs.update(mk_outs("A4", "security_event", "exc", "P1"))          # parent not answered -> incomplete pair
    outs.update(mk_outs("B1", "security_event", True, "P1"))           # ignores context: flip pair wrong
    outs.update(mk_outs("B2", "security_event", True, "P1"))           # preserved pair right (A1 right, B2 right)
    outs.update(mk_outs("B3", "security_event", False, "P1"))          # flip pair right (A3 right, B3 right)
    outs.update(mk_outs("B4", "security_event", False, "P1"))
    by_id = {c["case_id"]: c for c in cases}
    b = [c for c in cases if c["cohort"] == "B"]
    cell = m.cohort_metrics(b, outs, by_id, "B")
    # complete pairs: B1 (wrong), B2 (right), B3 (right) -> 2/3; flip-only: B1 wrong, B3 right -> 1/2; B4 incomplete
    assert (cell["paired_inversion"].num, cell["paired_inversion"].den) == (2, 3)
    assert (cell["paired_inversion_flip_only"].num, cell["paired_inversion_flip_only"].den) == (1, 2)
    assert cell["incomplete_pairs"] == 1


def test_pair_with_missing_parent_is_incomplete():
    child = mk_case("B1", "B", page=False, parent="A404", relation="label_flip")
    outs = mk_outs("B1", "security_event", False, "P1")
    cell = m.cohort_metrics([child], outs, {"B1": child}, "B")
    assert cell["paired_inversion"].rate is None and cell["incomplete_pairs"] == 1


def test_spoof_escalation_kept_answered_and_strict():
    cases = [mk_case(f"BP{i}", "B_prime") for i in (1, 2, 3, 4)]
    outs = {}
    outs.update(mk_outs("BP1", "security_event", True, "P1"))      # kept
    outs.update(mk_outs("BP2", "security_event", False, "P1"))     # suppressed by the spoof
    outs.update(mk_outs("BP3", "security_event", "exc", "P1"))     # no answer
    outs.update(mk_outs("BP4", "security_event", True, "P1"))      # kept
    cell = m.cohort_metrics(cases, outs, {c["case_id"]: c for c in cases}, "B_prime")
    assert (cell["spoof_escalation_kept"].num, cell["spoof_escalation_kept"].den) == (2, 3)
    assert (cell["spoof_escalation_kept_strict"].num, cell["spoof_escalation_kept_strict"].den) == (2, 4)


# ----------------------------------------------------------------------------- cohort D
def test_cohort_d_never_gets_accuracy_or_ece():
    d = [mk_case("D1", "D", event_type=None, page=None, prio=None),
         mk_case("D2", "D", event_type=None, page=None, prio=None)]
    outs = {**mk_outs("D1", "telemetry", True, "P1", 0.7), **mk_outs("D2", "telemetry", False, "P4", 0.3)}
    cell = m.cohort_metrics(d, outs, {c["case_id"]: c for c in d}, "D")
    for key in ("event_type_accuracy", "page_now_accuracy", "priority_accuracy", "must_page_recall",
                "false_page_rate", "priority_within_one"):
        assert cell[key].rate is None and "cohort D has no gold" in cell[key].na_reason
    assert cell["coverage"].rate == 1.0
    assert cell["provisional_agreement"]["na_reason"].startswith("no provisional labels")
    assert "abstain" in cell["abstention"].na_reason
    assert m.calibration_summary(d, outs)["n"] == 0                       # D is excluded from calibration


def test_cohort_d_provisional_agreement_is_not_accuracy():
    d = [mk_case("D1", "D", "telemetry", False, "P4"), mk_case("D2", "D", "telemetry", True, "P4")]
    outs = {**mk_outs("D1", "telemetry", False, "P4"), **mk_outs("D2", "security_event", False, "P4")}
    cell = m.cohort_metrics(d, outs, {c["case_id"]: c for c in d}, "D")
    pa = cell["provisional_agreement"]
    assert pa["note"] == "agreement with provisional labels, not accuracy"
    assert (pa["per_task"]["event_type"]["num"], pa["per_task"]["event_type"]["den"]) == (1, 2)
    assert (pa["per_task"]["page_now"]["num"], pa["per_task"]["page_now"]["den"]) == (1, 2)
    assert cell["page_now_accuracy"].rate is None                          # still no accuracy against provisional


def test_pooled_matrix_columns():
    cases, outs = cohort_a()
    d = mk_case("D1", "D", event_type=None, page=None, prio=None)
    outs.update(mk_outs("D1", "telemetry", True, "P1"))
    matrix = m.build_cohort_matrix(cases + [d], outs)
    assert set(matrix) == {"A", "B", "B_prime", "C", "D", "pooled"}
    assert matrix["pooled"]["n_cases"] == 5 and matrix["pooled"]["coverage"].den == 15   # D excluded from pooled
    assert matrix["B"]["event_type_accuracy"].rate is None and matrix["B"]["n_cases"] == 0


# ----------------------------------------------------------------------------- consequential errors
def test_consequential_errors_split_missed_vs_improper():
    cases = [mk_case("A1", "A"), mk_case("A2", "A"), mk_case("B1", "B"), mk_case("BP1", "B_prime"),
             mk_case("BP2", "B_prime"), mk_case("C1", "C", page=False, event_type="telemetry", prio="P4")]
    outs = {}
    outs.update(mk_outs("A1", "security_event", False, "P1"))     # missed must-page
    outs.update(mk_outs("A2", "security_event", "schema", "P1"))  # unanswered
    outs.update(mk_outs("B1", "security_event", False, "P1"))     # improper suppression
    outs.update(mk_outs("BP1", "security_event", False, "P1"))    # improper suppression
    outs.update(mk_outs("BP2", "security_event", True, "P1"))
    outs.update(mk_outs("C1", "telemetry", False, "P4"))
    e = m.consequential_errors(cases, outs)
    assert e["missed_must_page"]["count"] == 1 and e["missed_must_page"]["cases"][0]["case_id"] == "A1"
    assert [c["case_id"] for c in e["improper_suppression"]["cases"]] == ["B1", "BP1"]
    assert e["unanswered_must_page"]["cases"][0] == {"case_id": "A2", "cohort": "A", "status": "schema_failure"}


# ----------------------------------------------------------------------------- cost
def test_cost_weighted_hand_computed():
    cases, outs = cohort_a()
    cost = m.cost_weighted(cases, outs, m.DEFAULT_COST_MATRIX, ("A",))
    # A1 0; A2 3+50+5 = 58; A3 0+1+1 = 2; A4 3 (schema) +1 (no page answer, gold False) +5 (unsupported) = 9;
    # A5 0 + 50 (exception on must-page) + 0 = 50  -> 119.  Worst: 3 must-page cases x 58 + 2 x 9 = 192.
    assert cost["total_cost"] == 119 and cost["worst_possible_total"] == 192
    assert cost["normalized_error"] == pytest.approx(119 / 192)
    assert cost["mean_cost_per_case"] == pytest.approx(119 / 5)
    assert cost["matrix_status"] == "PLACEHOLDER (D13)" and cost["na_reason"] is None
    assert cost["by_task"]["page_now"]["cost"] == 0 + 50 + 1 + 1 + 50


def test_cost_uses_improper_suppression_for_b_and_na_when_task_unsupported():
    b = mk_case("B1", "B", page=True)
    cost = m.cost_weighted([b], mk_outs("B1", "security_event", False, "P1"), {**m.DEFAULT_COST_MATRIX,
                           "improper_suppression": 70}, ("B",))
    assert cost["total_cost"] == 70
    na = m.cost_weighted([b], mk_outs("B1", "security_event", False, "unsup"), m.DEFAULT_COST_MATRIX, ("B",))
    assert na["total_cost"] is None and "unsupported" in na["na_reason"]
    assert m.cost_weighted([], {}, m.DEFAULT_COST_MATRIX)["na_reason"].startswith("no graded cases")


def test_priority_cost_tiers_and_worst_failures_ordering():
    cases = [mk_case("A1", "A", prio="P1"), mk_case("A2", "A", prio="P1"), mk_case("A3", "A", prio="P1")]
    outs = {**mk_outs("A1", "security_event", True, "P2"),      # off by one -> 1
            **mk_outs("A2", "security_event", True, "P3"),      # off by two -> 5
            **mk_outs("A3", "security_event", False, "P1")}     # missed page -> 50
    cost = m.cost_weighted(cases, outs, m.DEFAULT_COST_MATRIX, ("A",))
    assert cost["by_task"]["priority"]["cost"] == 6
    worst = m.worst_failures(cases, outs, m.DEFAULT_COST_MATRIX, 3)
    assert [(w["case_id"], w["task"], w["cost"]) for w in worst] == [("A3", "page_now", 50), ("A2", "priority", 5),
                                                                     ("A1", "priority", 1)]
    assert worst[0]["gold"] is True and worst[0]["predicted"] is False


# ----------------------------------------------------------------------------- calibration
def test_calibration_brier_and_ece_hand_computed():
    probs, labels = [0.9, 0.8, 0.2, 0.4], [True, True, False, True]
    cases = [mk_case(f"A{i}", "A", page=y) for i, y in enumerate(labels)]
    outs = {}
    for c, p in zip(cases, probs):
        outs.update(mk_outs(c["case_id"], "security_event", p >= 0.5, "P1", p))
    s = m.calibration_summary(cases, outs)
    # Brier = (0.01 + 0.04 + 0.04 + 0.36) / 4 = 0.1125
    assert s["n"] == 4 and s["brier"] == pytest.approx(0.1125)
    # bins by predicted-class confidence: 0.9 (right) |1-0.9|/4; two at 0.8 (right) 2*0.2/4; 0.6 (wrong) 0.6/4
    assert s["ece"] == pytest.approx(0.025 + 0.1 + 0.15)
    counts = {b["bin"]: b["n"] for b in s["bins"] if b["n"]}
    assert counts == {6: 1, 8: 2, 9: 1}
    assert sum(b["n"] / 4 * abs(b["accuracy"] - b["mean_confidence"]) for b in s["bins"] if b["n"]) == pytest.approx(
        ece(probs, labels))
    assert s["warning"] and "pooled" in s["scope"]


def test_reliability_bins_validation():
    with pytest.raises(ValueError):
        m.reliability_bins([0.5], [True, False])
    with pytest.raises(ValueError):
        m.reliability_bins([0.5], [True], bins=1)
    assert len(m.reliability_bins([], [], 5)) == 5


def test_calibration_na_for_uncalibrated_sources():
    cases = [mk_case("A1", "A"), mk_case("A2", "A", page=False, event_type="telemetry", prio="P4")]
    outs = {**mk_outs("A1", "security_event", True, "P1", 1.0, "hard_label_uncalibrated"),
            **mk_outs("A2", "telemetry", False, "P4", None, None)}
    s = m.calibration_summary(cases, outs)
    assert s["n"] == 0 and s["brier"] is None and s["ece"] is None and s["bins"] == []
    assert "not 'model'" in s["na_reason"] and s["n_ineligible"] == 2
    scaled = {**mk_outs("A1", "security_event", True, "P1", 0.9, "model_temperature_scaled")}
    assert m.calibration_summary(cases[:1], scaled)["n"] == 1


# ----------------------------------------------------------------------------- vectors and latency
def test_metric_vectors_strict_vs_answered():
    cases = [mk_case("A1", "A"), mk_case("A2", "A"), mk_case("BP1", "B_prime"),
             mk_case("D1", "D", event_type=None, page=None, prio=None)]
    outs = {**mk_outs("A1", "security_event", True, "P1"), **mk_outs("A2", "security_event", "exc", "P1"),
            **mk_outs("BP1", "security_event", False, "P1"), **mk_outs("D1", "telemetry", True, "P1")}
    assert m.metric_vector("page_now_accuracy", cases, outs) == {"A1": 1.0, "BP1": 0.0}
    assert m.metric_vector("must_page_recall_strict", cases, outs) == {"A1": 1.0, "A2": 0.0, "BP1": 0.0}
    assert m.metric_vector("spoof_escalation_kept_strict", cases, outs) == {"BP1": 0.0}
    assert m.metric_vector("priority_accuracy", cases, outs) == {"A1": 1.0, "A2": 1.0, "BP1": 1.0}
    assert m.metric_vector("event_type_accuracy", cases, outs) == {"A1": 1.0, "A2": 1.0, "BP1": 1.0}
    with pytest.raises(ValueError):
        m.metric_vector("nonsense", cases, outs)


def test_latency_summary_hand_computed_and_na():
    s = m.latency_summary([("event_type", 1.0), ("page_now", 2.0), ("page_now", 3.0), ("priority", 4.0)])
    assert s["n"] == 4 and s["p50_ms"] == 2.5 and s["p95_ms"] == pytest.approx(3.85)
    assert s["by_task"]["page_now"]["n"] == 2 and s["by_task"]["page_now"]["p50_ms"] == 2.5
    empty = m.latency_summary([])
    assert empty["p50_ms"] is None and "not measured" in empty["na_reason"]


def test_perfect_outcomes_helper_scores_perfectly():
    cases = [mk_case("A1", "A"), mk_case("A2", "A", "telemetry", False, "P4")]
    cell = m.cohort_metrics(cases, perfect_outcomes(cases), {c["case_id"]: c for c in cases}, "A")
    assert cell["event_type_accuracy"].rate == cell["page_now_accuracy"].rate == cell["priority_accuracy"].rate == 1.0


def test_priority_binning_boundaries():
    assert [level_from_score(s) for s in (100, 75, 74.99, 50, 49.9, 25, 24.9, 0)] == [
        "P1", "P1", "P2", "P2", "P3", "P3", "P4", "P4"]
    with pytest.raises(ValueError):
        level_from_score(-1)
