"""Selection scorecard (PRACTICAL_EVAL_V2 section 5), WS4.

What this module is: a deterministic reduction of already-computed metrics to
hard-gate results and one of three selection outputs per candidate arm:
``recommended``, ``not recommended`` or ``insufficient evidence``.

What it is not: a deployment approval. A pass means only that the gates it could
evaluate were met on the data it saw. Classifier output never authorizes an
action (AGENTS.md rule 5), and synthetic results do not support a deployment
decision (only the S8 own-data suite can).

Gate states:
  pass           evidence clears the threshold
  fail           evidence is below the threshold
  inconclusive   the interval straddles the threshold (not enough cases)
  not_evaluated  the input is missing, unset, from the wrong hardware, or the
                 suite that supplies it is not built. Never a pass.

Thresholds, weights and the cost matrix come from ``configs/selection_scorecard.yaml``.
They are placeholders (D13); an unset budget (``p95_ms_max: null``, Q4) shows
"not evaluated".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evaluation.v2_data import TASKS
from evaluation.v2_metrics import (Proportion, build_cohort_matrix, cost_weighted, latency_summary, proportion,
                                   worst_failures)
from evaluation.v2_runner import CandidateRun

GATE_STATUSES = ("pass", "fail", "inconclusive", "not_evaluated")
VERDICTS = ("recommended", "not recommended", "insufficient evidence")
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "selection_scorecard.yaml"

NOT_DEPLOYMENT_APPROVAL = (
    "A pass is not deployment approval. These gates run on a synthetic harness fixture; only an own-data suite "
    "(S8) supports a deployment decision, and a deterministic authorization and audit layer must still sit between "
    "any classifier output and an action (AGENTS.md rule 5).")

NOT_BUILT = {
    "format_shift_drop": "S4 leave-one-source-out splits are not built (generator `not_implemented`)",
    "defer_quality": ("S5 needs adjudicated needs_human labels and an abstain output; cohort D is unlabeled and "
                      "the adapter interface has no abstain output"),
    "label_budget_to_target": "S7 label-budget subsets are not built",
    "throughput_eps": "S6 stream replay is not built",
    "explainability": "no automated evidence-pointer measure exists; needs reviewer input",
    "ops_fit": "needs owner input (size, cold start, update path, add-a-route effort)",
}

_TOP_KEYS = {"scorecard_version", "status", "confidence", "gate_rule", "hard_gates", "cost_matrix", "cost_cohorts",
             "weights", "modules", "selection"}
_GATE_KEYS = {"runs_offline_on_target", "license_ok_for_intended_use", "supports_all_three_tasks",
              "schema_valid_rate_min", "must_page_recall_min", "must_page_gate_cohorts", "spoof_escalation_kept_min",
              "false_pages_per_1k_max", "p95_ms_max", "min_timing_samples", "target_hardware_substring",
              "peak_memory_gb_max", "memory_reserve_gb", "host_memory_gb"}


class ScorecardConfigError(ValueError):
    pass


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read and strictly validate the scorecard config. Unknown keys and bad values raise."""
    path = Path(path or DEFAULT_CONFIG)
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"cannot read scorecard config {path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ScorecardConfigError("scorecard config must be a mapping")
    return validate_config(cfg)


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    missing = _TOP_KEYS - set(cfg)
    extra = set(cfg) - _TOP_KEYS
    if missing or extra:
        raise ScorecardConfigError(f"config keys: missing {sorted(missing)}, unknown {sorted(extra)}")
    gates = cfg["hard_gates"]
    if set(gates) != _GATE_KEYS:
        raise ScorecardConfigError(f"hard_gates keys: missing {sorted(_GATE_KEYS - set(gates))}, "
                                   f"unknown {sorted(set(gates) - _GATE_KEYS)}")
    if cfg["gate_rule"] not in ("wilson_bound", "point"):
        raise ScorecardConfigError("gate_rule must be 'wilson_bound' or 'point'")
    if abs(cfg["confidence"] - 0.95) > 1e-12:
        raise ScorecardConfigError("only 95% intervals are implemented (Wilson z=1.96); set confidence: 0.95")
    for key in ("schema_valid_rate_min", "must_page_recall_min", "spoof_escalation_kept_min"):
        if not 0 <= gates[key] <= 1:
            raise ScorecardConfigError(f"{key} must be within [0,1]")
    for key in ("p95_ms_max", "false_pages_per_1k_max"):
        if gates[key] is not None and gates[key] <= 0:
            raise ScorecardConfigError(f"{key} must be positive or null (unset)")
    for key in ("peak_memory_gb_max", "memory_reserve_gb", "host_memory_gb"):
        if gates[key] is None or gates[key] < 0:
            raise ScorecardConfigError(f"{key} must be a nonnegative number")
    weights = cfg["weights"]
    if set(weights) != set(NOT_BUILT) | {"cost_weighted_error", "spoof_robustness"}:
        raise ScorecardConfigError(f"unexpected weight keys {sorted(weights)}")
    if abs(sum(weights.values()) - 1.0) > 1e-9 or any(w < 0 for w in weights.values()):
        raise ScorecardConfigError(f"weights must be nonnegative and sum to 1.0, got {sum(weights.values())}")
    if set(cfg["cost_matrix"]) != {"missed_must_page", "improper_suppression", "false_page", "wrong_queue",
                                   "priority_off_by_one", "priority_off_by_two_plus"}:
        raise ScorecardConfigError("cost_matrix keys do not match the v2 cost matrix")
    chat = cfg["modules"].get("chat", {})
    if not isinstance(chat.get("enabled"), bool) or not 0 <= chat.get("weight", -1) <= 1:
        raise ScorecardConfigError("modules.chat needs enabled: bool and weight in [0,1]")
    if not 0 <= cfg["selection"]["min_weight_coverage"] <= 1:
        raise ScorecardConfigError("selection.min_weight_coverage must be within [0,1]")
    return cfg


def effective_memory_gate_gb(cap_gb: float, host_gb: float, baseline_other_gb: float, reserve_gb: float) -> float:
    """D12: min(cap, host - baseline of other processes - reserve). May be <= 0 (no headroom)."""
    return min(cap_gb, host_gb - baseline_other_gb - reserve_gb)


def _gate(name: str, status: str, threshold: Any, detail: str, measured: Any = None) -> dict[str, Any]:
    assert status in GATE_STATUSES
    return {"name": name, "status": status, "threshold": threshold, "measured": measured, "detail": detail}


def _decide_min(name: str, p: Proportion, threshold: float, rule: str, what: str) -> dict[str, Any]:
    measured = p.to_dict()
    if p.den == 0:
        return _gate(name, "not_evaluated", threshold, f"{what}: no cases in the denominator ({p.na_reason})")
    text = f"{what}: {p.num}/{p.den} = {p.rate:.3f}, Wilson95 [{p.low:.3f}, {p.high:.3f}], need >= {threshold}"
    if rule == "point":
        return _gate(name, "pass" if p.rate >= threshold else "fail", threshold, text + " (point rule)", measured)
    if p.low >= threshold:
        return _gate(name, "pass", threshold, text + " (lower bound clears)", measured)
    if p.high < threshold:
        return _gate(name, "fail", threshold, text + " (upper bound below)", measured)
    return _gate(name, "inconclusive", threshold, text + " (interval straddles the threshold: too few cases)", measured)


def _sum_cells(matrix: dict[str, Any], cohorts: list[str], key: str) -> Proportion:
    num = sum(matrix[c][key].num for c in cohorts)
    den = sum(matrix[c][key].den for c in cohorts)
    return proportion(num, den, f"no cases in cohorts {cohorts}")


def _schema_valid(run: CandidateRun) -> Proportion:
    outs = list(run.test.values())
    ok = sum(o.status == "ok" for o in outs)
    attempted = ok + sum(o.status in ("schema_failure", "exception") for o in outs)
    return proportion(ok, attempted, "no attempted calls")


def _operational_gates(cfg: dict[str, Any], run: CandidateRun, hardware: str) -> list[dict[str, Any]]:
    g, op = cfg["hard_gates"], run.spec.operational
    gates = []
    if g["runs_offline_on_target"]:
        v = op.get("offline_verified")
        gates.append(_gate("runs_offline_on_target", "not_evaluated" if v is None else ("pass" if v else "fail"), True,
                           "no offline-operation attestation supplied" if v is None
                           else f"offline_verified={v} (attested by the caller, not measured here)"))
    if g["license_ok_for_intended_use"]:
        v = op.get("license_ok")
        gates.append(_gate("license_ok_for_intended_use", "not_evaluated" if v is None else ("pass" if v else "fail"),
                           True, "no licence review supplied" if v is None else f"license_ok={v} (attested)"))
    # p95 latency
    budget = g["p95_ms_max"]
    lat = run.timing
    p95 = None
    if run.latencies:
        p95 = latency_summary(run.latencies)["p95_ms"]
    on_target = bool(g["target_hardware_substring"]) and g["target_hardware_substring"] in hardware
    if budget is None:
        gates.append(_gate("p95_ms_max", "not_evaluated", None, "budget unset (Q4 is open): not evaluated"))
    elif not run.latencies:
        gates.append(_gate("p95_ms_max", "not_evaluated", budget, "no timing samples were taken"))
    elif len(run.latencies) < g["min_timing_samples"]:
        gates.append(_gate("p95_ms_max", "not_evaluated", budget,
                           f"{len(run.latencies)} timing samples, need >= {g['min_timing_samples']}"))
    elif not (on_target and op.get("latency_hardware_is_target", True)):
        gates.append(_gate("p95_ms_max", "not_evaluated", budget,
                           f"timed on '{hardware}', not target hardware (needs '{g['target_hardware_substring']}')"))
    else:
        gates.append(_gate("p95_ms_max", "pass" if p95 <= budget else "fail", budget,
                           f"p95 {p95:.1f} ms over {len(run.latencies)} samples, need <= {budget} ms", p95))
    # memory (D12)
    peak, base = op.get("peak_memory_gb"), op.get("baseline_other_gb")
    cap, host, reserve = g["peak_memory_gb_max"], g["host_memory_gb"], g["memory_reserve_gb"]
    if peak is None or base is None:
        gates.append(_gate("peak_memory_gb", "not_evaluated", cap,
                           "peak memory or the preflight baseline was not measured (needs the Mac; method open)"))
    elif op.get("memory_pressure_normal") is not True or op.get("swap_grew") is not False:
        gates.append(_gate("peak_memory_gb", "not_evaluated", cap,
                           "run invalid, not failed: memory pressure left normal or swap grew (or was not recorded)"))
    else:
        eff = effective_memory_gate_gb(cap, host, base, reserve)
        if eff <= 0:
            gates.append(_gate("peak_memory_gb", "not_evaluated", eff,
                               f"no headroom: effective gate {eff:.1f} GB (baseline {base} GB); run invalid"))
        else:
            gates.append(_gate("peak_memory_gb", "pass" if peak <= eff else "fail", eff,
                               f"peak {peak} GB vs effective gate min({cap}, {host} - {base} - {reserve}) = {eff} GB",
                               peak))
    return gates


def _chat_gates(cfg: dict[str, Any], key: str, chat: dict[str, Any] | None) -> list[dict[str, Any]]:
    mod = cfg["modules"]["chat"]
    if not mod["enabled"]:
        return []
    gates = []
    row = ((chat or {}).get("rows") or {}).get(key)
    for gate_key, field in (("must_page_recall_min", "must_page_recall"), ("spoof_recall_min", "spoof_recall")):
        name = f"chat_{gate_key}"
        if not row or field not in row:
            gates.append(_gate(name, "not_evaluated", mod["hard_gates"][gate_key], "no S9 chat results supplied"))
        else:
            p = proportion(int(row[field]["num"]), int(row[field]["den"]), "no chat cases")
            gates.append(_decide_min(name, p, mod["hard_gates"][gate_key], cfg["gate_rule"], f"S9 {field}"))
    return gates


def evaluate_candidate(cfg: dict[str, Any], run: CandidateRun, test_cases: list[dict[str, Any]],
                       hardware: str, purpose: str = "plumbing_check",
                       chat: dict[str, Any] | None = None) -> dict[str, Any]:
    """One scorecard row for a candidate arm."""
    row: dict[str, Any] = {"candidate": run.spec.name, "arm": run.spec.arm, "status": run.status,
                           "matrix_status": "PLACEHOLDER (D13)", "gates": [], "components": {}, "worst_failures": [],
                           "weight_coverage": 0.0, "partial_score": None, "verdict": None, "reasons": [],
                           "notice": NOT_DEPLOYMENT_APPROVAL}
    if run.status == "unavailable" or run.test is None:
        row["verdict"] = "insufficient evidence"
        row["reasons"] = [f"candidate unavailable: {run.note or run.spec.unavailable_reason}"]
        return row
    g, rule = cfg["hard_gates"], cfg["gate_rule"]
    matrix = build_cohort_matrix(test_cases, run.test)
    gates: list[dict[str, Any]] = _operational_gates(cfg, run, hardware)
    if g["supports_all_three_tasks"]:
        unsupported = sorted({k[1] for k, o in run.test.items() if o.status == "unsupported"}, key=TASKS.index)
        gates.append(_gate("supports_all_three_tasks", "fail" if unsupported else "pass", True,
                           f"unsupported tasks: {unsupported}" if unsupported else "all three tasks answered or attempted"))
    gates.append(_decide_min("schema_valid_rate_min", _schema_valid(run), g["schema_valid_rate_min"], rule,
                             "schema-valid rate over attempted calls"))
    cohorts = g["must_page_gate_cohorts"]
    gates.append(_decide_min("must_page_recall_min", _sum_cells(matrix, cohorts, "must_page_recall_strict"),
                             g["must_page_recall_min"], rule,
                             f"strict must-page recall, cohorts {cohorts}, non-answers count as misses"))
    gates.append(_decide_min("spoof_escalation_kept_min", matrix["B_prime"]["spoof_escalation_kept_strict"],
                             g["spoof_escalation_kept_min"], rule,
                             "B' escalation kept (strict), payload claims must not suppress a page"))
    fp = run.spec.operational.get("false_pages_per_1k_s6")
    if g["false_pages_per_1k_max"] is None:
        gates.append(_gate("false_pages_per_1k_max", "not_evaluated", None, "threshold unset"))
    elif fp is None:
        gates.append(_gate("false_pages_per_1k_max", "not_evaluated", g["false_pages_per_1k_max"],
                           "needs the S6 stream at realistic prevalence, which is not built; the balanced-set "
                           "false-page rate is a diagnostic and is not scaled to per-1k"))
    else:
        gates.append(_gate("false_pages_per_1k_max", "pass" if fp <= g["false_pages_per_1k_max"] else "fail",
                           g["false_pages_per_1k_max"], f"{fp} false pages per 1k (S6), point rule", fp))
    gates.extend(_chat_gates(cfg, run.spec.key, chat))
    row["gates"] = gates

    # weighted components (only what is computable; nothing is renormalized silently)
    weights = dict(cfg["weights"])
    chat_cfg = cfg["modules"]["chat"]
    if chat_cfg["enabled"]:
        weights = {k: w * (1 - chat_cfg["weight"]) for k, w in weights.items()}
        weights["chat_module"] = chat_cfg["weight"]
    cost = cost_weighted(test_cases, run.test, cfg["cost_matrix"], tuple(cfg["cost_cohorts"]))
    row["cost"] = cost
    comps: dict[str, dict[str, Any]] = {}
    comps["cost_weighted_error"] = _component(weights["cost_weighted_error"],
                                              None if cost["normalized_error"] is None else 1 - cost["normalized_error"],
                                              cost["na_reason"] or "1 - cost / worst possible cost (placeholder matrix)")
    kept = matrix["B_prime"]["spoof_escalation_kept_strict"]
    comps["spoof_robustness"] = _component(weights["spoof_robustness"], kept.rate,
                                           "B' escalation kept (strict)" if kept.den else str(kept.na_reason))
    for name, reason in NOT_BUILT.items():
        comps[name] = _component(weights[name], None, reason)
    if chat_cfg["enabled"]:
        comps["chat_module"] = _component(weights["chat_module"], None,
                                          "S9 has no weighted-score definition and no runner yet")
    row["components"] = comps
    covered = sum(c["weight"] for c in comps.values() if c["score"] is not None)
    row["weight_coverage"] = covered
    if covered > 0:
        row["partial_score"] = sum(c["weight"] * c["score"] for c in comps.values() if c["score"] is not None) / covered
    row["worst_failures"] = worst_failures(test_cases, run.test, cfg["cost_matrix"], 3)
    _verdict(cfg, row, purpose)
    return row


def _component(weight: float, score: float | None, reason: str) -> dict[str, Any]:
    return {"weight": weight, "score": score, "status": "evaluated" if score is not None else "not_evaluated",
            "note": reason}


def _verdict(cfg: dict[str, Any], row: dict[str, Any], purpose: str) -> None:
    failed = [g for g in row["gates"] if g["status"] == "fail"]
    open_ = [g for g in row["gates"] if g["status"] in ("inconclusive", "not_evaluated")]
    need = cfg["selection"]["min_weight_coverage"]
    short = row["weight_coverage"] + 1e-12 < need
    plumbing = purpose != "measurement"
    reasons: list[str] = []
    if plumbing:
        # A plumbing check proves the harness runs. It never yields a verdict either way.
        verdict = "insufficient evidence"
        reasons.append(f"purpose is '{purpose}': a plumbing check cannot produce a recommendation or a rejection")
        reasons += [f"gate failed (observed, not a verdict): {g['name']}: {g['detail']}" for g in failed]
    elif failed:
        verdict = "not recommended"
        reasons += [f"gate failed: {g['name']}: {g['detail']}" for g in failed]
    elif open_ or short:
        verdict = "insufficient evidence"
    else:
        verdict = "recommended"
        reasons.append("every hard gate passed and the required weight coverage was evaluated")
    if verdict != "not recommended":
        reasons += [f"gate {g['status'].replace('_', ' ')}: {g['name']}: {g['detail']}" for g in open_]
        if short:
            reasons.append(f"only {row['weight_coverage']:.0%} of the scorecard weight could be evaluated "
                           f"(need {need:.0%}); not evaluated: "
                           + ", ".join(k for k, c in row["components"].items() if c["score"] is None))
    row["verdict"] = verdict
    row["reasons"] = reasons
