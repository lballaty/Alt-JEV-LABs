"""Scorecard gates, unset-gate behaviour, memory formula, cost weighting and verdicts."""

import copy

import pytest

from evaluation import scorecard as sc
from evaluation.v2_metrics import proportion
from evaluation.v2_runner import CandidateRun, CandidateSpec
from v2_fixtures import StubAlwaysPage, mk_case, mk_outs, perfect_outcomes

M4 = "Apple M4 Max; 128.0 GiB unified memory"
GOOD_OPS = {"offline_verified": True, "license_ok": True, "peak_memory_gb": 40.0, "baseline_other_gb": 20.0,
            "memory_pressure_normal": True, "swap_grew": False, "false_pages_per_1k_s6": 5.0}


def big_cases():
    """600 hand-made graded cases: enough that a perfect candidate clears every Wilson bound."""
    cases = []
    for i in range(300):
        cases.append(mk_case(f"A{i}", "A", "security_event", True, "P1") if i % 2 == 0
                     else mk_case(f"A{i}", "A", "telemetry", False, "P4"))
    cases += [mk_case(f"BP{i}", "B_prime", "security_event", True, "P1") for i in range(100)]
    cases += [mk_case(f"B{i}", "B", "security_event", i % 2 == 0, "P2") for i in range(100)]
    cases += [mk_case(f"C{i}", "C", "security_event", True, "P1") for i in range(100)]
    return cases


def run_for(cases, outs=None, operational=None, latencies=None, status="measured"):
    spec = CandidateSpec("cand", "raw", StubAlwaysPage(), operational=dict(operational or {}))
    return CandidateRun(spec, status, outs if outs is not None else perfect_outcomes(cases),
                        perfect_outcomes(cases), latencies if latencies is not None else [],
                        {"status": "measured"})


def gate(row, name):
    return next(g for g in row["gates"] if g["name"] == name)


@pytest.fixture
def cfg():
    return sc.load_config()


@pytest.fixture
def lenient(cfg):
    """Default config but accepting the 45% of weight WS4 can compute, and a set p95 budget."""
    c = copy.deepcopy(cfg)
    c["selection"]["min_weight_coverage"] = 0.45
    c["hard_gates"]["p95_ms_max"] = 250
    return c


# ----------------------------------------------------------------------------- config
def test_default_config_loads_and_is_a_placeholder(cfg):
    assert cfg["hard_gates"]["p95_ms_max"] is None                 # Q4 is open
    assert cfg["hard_gates"]["peak_memory_gb_max"] == 96 and cfg["hard_gates"]["memory_reserve_gb"] == 16
    assert cfg["hard_gates"]["host_memory_gb"] == 128 and "PLACEHOLDER" in cfg["status"]
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert cfg["modules"]["chat"]["enabled"] is False


@pytest.mark.parametrize("mutate,message", [
    (lambda c: c.pop("weights"), "missing"),
    (lambda c: c.update(extra=1), "unknown"),
    (lambda c: c["hard_gates"].update(bogus=1), "hard_gates keys"),
    (lambda c: c.update(gate_rule="vibes"), "gate_rule"),
    (lambda c: c.update(confidence=0.9), "95%"),
    (lambda c: c["hard_gates"].update(schema_valid_rate_min=1.5), "within"),
    (lambda c: c["hard_gates"].update(p95_ms_max=-5), "positive or null"),
    (lambda c: c["hard_gates"].update(peak_memory_gb_max=None), "nonnegative"),
    (lambda c: c["weights"].update(ops_fit=0.5), "sum to 1.0"),
    (lambda c: c["weights"].update(surprise=0.0), "weight keys"),
    (lambda c: c["cost_matrix"].pop("false_page"), "cost_matrix"),
    (lambda c: c["modules"]["chat"].update(enabled="true"), "modules.chat"),
    (lambda c: c["selection"].update(min_weight_coverage=2), "min_weight_coverage"),
])
def test_invalid_configs_are_rejected(cfg, mutate, message):
    bad = copy.deepcopy(cfg)
    mutate(bad)
    with pytest.raises(sc.ScorecardConfigError, match=message):
        sc.validate_config(bad)


def test_unreadable_config_raises(tmp_path):
    with pytest.raises(sc.ScorecardConfigError, match="cannot read"):
        sc.load_config(tmp_path / "missing.yaml")
    (tmp_path / "list.yaml").write_text("- 1\n")
    with pytest.raises(sc.ScorecardConfigError, match="mapping"):
        sc.load_config(tmp_path / "list.yaml")


# ----------------------------------------------------------------------------- proportion gates
def test_decision_rules():
    thr = 0.95
    clear = sc._decide_min("g", proportion(1000, 1000), thr, "wilson_bound", "x")
    straddle = sc._decide_min("g", proportion(29, 30), thr, "wilson_bound", "x")
    below = sc._decide_min("g", proportion(60, 100), thr, "wilson_bound", "x")
    empty = sc._decide_min("g", proportion(0, 0), thr, "wilson_bound", "x")
    assert (clear["status"], straddle["status"], below["status"], empty["status"]) == (
        "pass", "inconclusive", "fail", "not_evaluated")
    # the same 29/30 under the point rule: 0.967 >= 0.95 passes
    assert sc._decide_min("g", proportion(29, 30), thr, "point", "x")["status"] == "pass"
    assert sc._decide_min("g", proportion(28, 30), thr, "point", "x")["status"] == "fail"


# ----------------------------------------------------------------------------- unset and missing gates
def test_unset_p95_budget_is_not_evaluated_even_with_fast_timing(cfg):
    cases = big_cases()
    row = sc.evaluate_candidate(cfg, run_for(cases, latencies=[("page_now", 1.0)] * 500), cases, M4, "measurement")
    g = gate(row, "p95_ms_max")
    assert g["status"] == "not_evaluated" and "unset" in g["detail"] and g["threshold"] is None
    assert row["verdict"] != "recommended"


def test_p95_gate_conditions(lenient):
    cases = big_cases()
    fast = [("page_now", 10.0)] * 100
    on = sc.evaluate_candidate(lenient, run_for(cases, latencies=fast), cases, M4, "measurement")
    assert gate(on, "p95_ms_max")["status"] == "pass"
    slow = sc.evaluate_candidate(lenient, run_for(cases, latencies=[("page_now", 400.0)] * 100), cases, M4, "measurement")
    assert gate(slow, "p95_ms_max")["status"] == "fail" and slow["verdict"] == "not recommended"
    few = sc.evaluate_candidate(lenient, run_for(cases, latencies=fast[:10]), cases, M4, "measurement")
    assert gate(few, "p95_ms_max")["status"] == "not_evaluated" and "need >= 100" in gate(few, "p95_ms_max")["detail"]
    linux = sc.evaluate_candidate(lenient, run_for(cases, latencies=fast), cases, "x86_64 (non-Apple validation host)",
                                  "measurement")
    assert gate(linux, "p95_ms_max")["status"] == "not_evaluated" and "not target hardware" in gate(linux, "p95_ms_max")["detail"]
    none = sc.evaluate_candidate(lenient, run_for(cases), cases, M4, "measurement")
    assert "no timing samples" in gate(none, "p95_ms_max")["detail"]
    flagged = run_for(cases, operational={"latency_hardware_is_target": False}, latencies=fast)
    assert gate(sc.evaluate_candidate(lenient, flagged, cases, M4, "measurement"), "p95_ms_max")["status"] == "not_evaluated"


def test_effective_memory_gate_formula():
    assert sc.effective_memory_gate_gb(96, 128, 10, 16) == 96          # cap binds: 128-10-16 = 102
    assert sc.effective_memory_gate_gb(96, 128, 30, 16) == 82          # headroom binds
    assert sc.effective_memory_gate_gb(96, 128, 120, 16) == -8         # no headroom


def test_memory_gate_states(lenient):
    cases = big_cases()

    def mem(**ops):
        row = sc.evaluate_candidate(lenient, run_for(cases, operational=ops), cases, M4, "measurement")
        return gate(row, "peak_memory_gb")

    base = {"memory_pressure_normal": True, "swap_grew": False}
    assert mem()["status"] == "not_evaluated" and "not measured" in mem()["detail"]
    assert mem(peak_memory_gb=50.0)["status"] == "not_evaluated"                 # baseline missing
    ok = mem(peak_memory_gb=80.0, baseline_other_gb=10.0, **base)
    assert ok["status"] == "pass" and ok["threshold"] == 96
    tight = mem(peak_memory_gb=80.0, baseline_other_gb=40.0, **base)             # effective = 128-40-16 = 72
    assert tight["status"] == "fail" and tight["threshold"] == 72
    assert mem(peak_memory_gb=10.0, baseline_other_gb=10.0, memory_pressure_normal=False, swap_grew=False)[
        "status"] == "not_evaluated"
    assert "invalid" in mem(peak_memory_gb=10.0, baseline_other_gb=10.0, memory_pressure_normal=True,
                            swap_grew=True)["detail"]
    assert mem(peak_memory_gb=10.0, baseline_other_gb=10.0)["status"] == "not_evaluated"   # flags unrecorded
    assert "no headroom" in mem(peak_memory_gb=1.0, baseline_other_gb=120.0, **base)["detail"]


def test_attested_gates_default_to_not_evaluated(lenient):
    cases = big_cases()
    row = sc.evaluate_candidate(lenient, run_for(cases), cases, M4, "measurement")
    assert gate(row, "runs_offline_on_target")["status"] == "not_evaluated"
    assert gate(row, "license_ok_for_intended_use")["status"] == "not_evaluated"
    bad = sc.evaluate_candidate(lenient, run_for(cases, operational={"offline_verified": False, "license_ok": False}),
                                cases, M4, "measurement")
    assert gate(bad, "runs_offline_on_target")["status"] == "fail" and bad["verdict"] == "not recommended"
    off = copy.deepcopy(lenient)
    off["hard_gates"]["runs_offline_on_target"] = False
    names = [g["name"] for g in sc.evaluate_candidate(off, run_for(cases), cases, M4, "measurement")["gates"]]
    assert "runs_offline_on_target" not in names


def test_s6_gate_needs_the_stream(lenient):
    cases = big_cases()
    none = sc.evaluate_candidate(lenient, run_for(cases), cases, M4, "measurement")
    assert gate(none, "false_pages_per_1k_max")["status"] == "not_evaluated" and "S6" in gate(none, "false_pages_per_1k_max")["detail"]
    over = sc.evaluate_candidate(lenient, run_for(cases, operational={"false_pages_per_1k_s6": 30.0}), cases, M4, "measurement")
    assert gate(over, "false_pages_per_1k_max")["status"] == "fail"
    unset = copy.deepcopy(lenient)
    unset["hard_gates"]["false_pages_per_1k_max"] = None
    assert gate(sc.evaluate_candidate(unset, run_for(cases), cases, M4, "measurement"),
                "false_pages_per_1k_max")["detail"] == "threshold unset"


# ----------------------------------------------------------------------------- verdicts
def passing_run(cases, **kw):
    return run_for(cases, operational=GOOD_OPS, latencies=[("page_now", 10.0)] * 100, **kw)


def test_recommended_only_when_every_gate_passes_and_weight_is_covered(lenient, cfg):
    cases = big_cases()
    row = sc.evaluate_candidate(lenient, passing_run(cases), cases, M4, "measurement")
    assert [g["status"] for g in row["gates"]] == ["pass"] * len(row["gates"]), row["gates"]
    assert row["verdict"] == "recommended" and row["weight_coverage"] == pytest.approx(0.45)
    assert row["partial_score"] == pytest.approx(1.0)                          # perfect on both computable components
    assert "not deployment approval" in row["notice"]
    # the conservative default needs 100% of the weight, which S4-S7 etc. cannot supply yet
    strict = copy.deepcopy(lenient)
    strict["selection"]["min_weight_coverage"] = 1.0
    row2 = sc.evaluate_candidate(strict, passing_run(cases), cases, M4, "measurement")
    assert row2["verdict"] == "insufficient evidence" and any("45%" in r for r in row2["reasons"])


def test_plumbing_check_never_recommends_or_rejects(lenient):
    cases = big_cases()
    good = sc.evaluate_candidate(lenient, passing_run(cases), cases, M4, "plumbing_check")
    assert good["verdict"] == "insufficient evidence" and "plumbing check" in good["reasons"][0]
    blind = {c["case_id"]: False for c in cases}
    bad = sc.evaluate_candidate(lenient, passing_run(cases, outs=perfect_outcomes(cases, blind)), cases, M4,
                                "plumbing_check")
    assert bad["verdict"] == "insufficient evidence"
    assert any(r.startswith("gate failed (observed, not a verdict)") for r in bad["reasons"])


def test_failing_must_page_and_spoof_gates_reject(lenient):
    cases = big_cases()
    suppressed = {c["case_id"]: False for c in cases if c["cohort"] == "B_prime"}
    run = passing_run(cases, outs=perfect_outcomes(cases, suppressed))
    row = sc.evaluate_candidate(lenient, run, cases, M4, "measurement")
    assert gate(row, "spoof_escalation_kept_min")["status"] == "fail"
    assert gate(row, "must_page_recall_min")["status"] == "fail"       # A + B' strict: 150/250 = 0.6
    assert row["verdict"] == "not recommended" and any("spoof_escalation_kept_min" in r for r in row["reasons"])
    assert row["components"]["spoof_robustness"]["score"] == 0.0
    assert row["worst_failures"][0]["cost"] == 50 and len(row["worst_failures"]) == 3


def test_small_n_is_inconclusive_not_pass():
    cfg = sc.load_config()
    cfg["selection"]["min_weight_coverage"] = 0.0
    cases = [mk_case(f"A{i}", "A") for i in range(20)] + [mk_case(f"BP{i}", "B_prime") for i in range(9)]
    row = sc.evaluate_candidate(cfg, passing_run(cases), cases, M4, "measurement")
    assert gate(row, "must_page_recall_min")["status"] == "inconclusive"
    assert gate(row, "spoof_escalation_kept_min")["status"] == "inconclusive"
    assert row["verdict"] == "insufficient evidence"


def test_unsupported_task_fails_the_coverage_gate(lenient):
    cases = big_cases()
    outs = perfect_outcomes(cases)
    for c in cases:
        outs[(c["case_id"], "priority")] = outs[(c["case_id"], "priority")].__class__(
            c["case_id"], "priority", "unsupported")
    row = sc.evaluate_candidate(lenient, passing_run(cases, outs=outs), cases, M4, "measurement")
    g = gate(row, "supports_all_three_tasks")
    assert g["status"] == "fail" and "priority" in g["detail"]
    assert row["cost"]["total_cost"] is None and row["components"]["cost_weighted_error"]["score"] is None
    assert row["verdict"] == "not recommended"


def test_unavailable_candidate_is_insufficient_evidence(cfg):
    spec = CandidateSpec("laya", "raw", None, unavailable_reason="needs Mac")
    row = sc.evaluate_candidate(cfg, CandidateRun(spec, "unavailable", note="needs Mac"), [], M4, "measurement")
    assert row["verdict"] == "insufficient evidence" and row["gates"] == [] and "needs Mac" in row["reasons"][0]


def test_cost_component_uses_the_placeholder_matrix(lenient):
    cases = [mk_case("A1", "A", prio="P1"), mk_case("A2", "A", "telemetry", False, "P4")]
    outs = {**mk_outs("A1", "security_event", True, "P2"), **mk_outs("A2", "telemetry", False, "P4")}
    row = sc.evaluate_candidate(lenient, run_for(cases, outs=outs), cases, M4, "measurement")
    # A1 priority off by one -> 1. Worst: A1 3+50+5 = 58, A2 3+1+5 = 9 -> 67. normalized 1/67.
    assert row["cost"]["total_cost"] == 1 and row["cost"]["worst_possible_total"] == 67
    assert row["components"]["cost_weighted_error"]["score"] == pytest.approx(1 - 1 / 67)
    assert row["matrix_status"] == "PLACEHOLDER (D13)"
    assert row["components"]["defer_quality"]["status"] == "not_evaluated"


def test_schema_gate_counts_exceptions_as_not_valid(lenient):
    cases = big_cases()
    outs = perfect_outcomes(cases)
    outs[("A0", "priority")] = outs[("A0", "priority")].__class__("A0", "priority", "exception", error="x")
    run = passing_run(cases, outs=outs)
    g = gate(sc.evaluate_candidate(lenient, run, cases, M4, "measurement"), "schema_valid_rate_min")
    assert g["measured"]["num"] == 1799 and g["measured"]["den"] == 1800


# ----------------------------------------------------------------------------- chat module
def test_chat_gates_and_weights(lenient):
    cases = big_cases()
    chat_cfg = copy.deepcopy(lenient)
    chat_cfg["modules"]["chat"]["enabled"] = True
    off = sc.evaluate_candidate(lenient, passing_run(cases), cases, M4, "measurement")
    assert not [g for g in off["gates"] if g["name"].startswith("chat_")]
    row = sc.evaluate_candidate(chat_cfg, passing_run(cases), cases, M4, "measurement")
    chat_gates = [g for g in row["gates"] if g["name"].startswith("chat_")]
    assert {g["status"] for g in chat_gates} == {"not_evaluated"} and "no S9 chat results" in chat_gates[0]["detail"]
    assert sum(c["weight"] for c in row["components"].values()) == pytest.approx(1.0)
    assert row["components"]["chat_module"]["weight"] == 0.15
    assert row["components"]["cost_weighted_error"]["weight"] == pytest.approx(0.30 * 0.85)
    results = {"rows": {"cand/raw": {"must_page_recall": {"num": 500, "den": 500},
                                       "spoof_recall": {"num": 100, "den": 500}}}}
    row2 = sc.evaluate_candidate(chat_cfg, passing_run(cases), cases, M4, "measurement", chat=results)
    by = {g["name"]: g["status"] for g in row2["gates"]}
    assert by["chat_must_page_recall_min"] == "pass" and by["chat_spoof_recall_min"] == "fail"
