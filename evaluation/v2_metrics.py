"""Pure metrics for the v2 cohort matrix (WS4). No model, I/O or clock here.

Conventions that matter when reading a number from this module:

* Every rate is a ``Proportion`` with numerator, denominator and a Wilson 95%
  interval. A zero denominator is ``N/A`` with a stated reason, never 0.
* An outcome has one of four statuses: ``ok``, ``schema_failure``,
  ``exception`` or ``unsupported``. Accuracy-type metrics use *answered* calls as
  the denominator, so a backend error is never counted as a wrong prediction
  (AGENTS.md rule 8). Safety-critical figures (must-page recall, spoof
  escalation kept) also have a *strict* form in which every non-answer counts
  as a miss; the scorecard gates use the strict form.
* Cohort D has no gold. No accuracy, no ECE and no calibration is computed for
  it. Only coverage, failures and, if provisional labels are ever present,
  agreement with them (named agreement, not accuracy).
* Confidence intervals assume independent cases. Cases that share a pair or a
  template group are not independent, so Wilson intervals here are optimistic;
  the paired bootstrap resamples whole groups instead.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from evaluation.metrics import brier, ece, percentile
from evaluation.v2_data import GRADED_COHORTS, PRIORITY_INDEX, TASKS, gold

Z95 = 1.959963984540054
STATUSES = ("ok", "schema_failure", "exception", "unsupported")
NOT_DEFINED = "not defined for this cohort"
# Probability sources that are real model probabilities (raw, or validation-scaled from raw).
CALIBRATABLE_SOURCES = ("model", "model_temperature_scaled")

DEFAULT_COST_MATRIX = {
    "missed_must_page": 50, "improper_suppression": 50, "false_page": 1,
    "wrong_queue": 3, "priority_off_by_one": 1, "priority_off_by_two_plus": 5,
}


# --------------------------------------------------------------------------- outcomes
@dataclass(frozen=True)
class Outcome:
    """One (case, task) call. ``value`` is an event type, a bool page decision or a P level."""

    case_id: str
    task: str
    status: str
    value: Any = None
    probability: float | None = None
    probability_source: str | None = None
    raw_score: float | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown outcome status {self.status!r}")
        if self.task not in TASKS:
            raise ValueError(f"unknown task {self.task!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OutcomeMap = dict[tuple[str, str], Outcome]


# --------------------------------------------------------------------------- proportions
def wilson_interval(num: int, den: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion; None when ``den`` is 0."""
    if den < 0 or not 0 <= num <= den:
        raise ValueError(f"invalid counts {num}/{den}")
    if den == 0:
        return None
    p = num / den
    z2 = z * z
    denom = 1 + z2 / den
    centre = (p + z2 / (2 * den)) / denom
    half = z * math.sqrt(p * (1 - p) / den + z2 / (4 * den * den)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Proportion:
    num: int
    den: int
    low: float | None
    high: float | None
    na_reason: str | None = None

    @property
    def rate(self) -> float | None:
        return None if self.den == 0 else self.num / self.den

    def to_dict(self) -> dict[str, Any]:
        return {"num": self.num, "den": self.den, "rate": self.rate, "ci_low": self.low,
                "ci_high": self.high, "ci_method": "wilson95", "na_reason": self.na_reason}


def proportion(num: int, den: int, na_reason: str | None = None) -> Proportion:
    ci = wilson_interval(num, den)
    if ci is None:
        return Proportion(num, den, None, None, na_reason or "no cases in the denominator")
    return Proportion(num, den, ci[0], ci[1], None)


def not_applicable(reason: str) -> Proportion:
    return Proportion(0, 0, None, None, reason)


# --------------------------------------------------------------------------- paired bootstrap
def paired_bootstrap_diff(a: dict[str, float], b: dict[str, float], clusters: dict[str, str],
                          seed: int, n_boot: int = 2000, confidence: float = 0.95) -> dict[str, Any]:
    """Paired difference mean(a) - mean(b) over the cases both candidates have.

    ``a`` and ``b`` map case_id to a per-case value (0/1 or numeric). Only case
    ids present in both are used, so both candidates are compared on identical
    cases. The bootstrap resamples whole clusters (pair or template group)
    with replacement because cases inside a cluster are not independent; the
    percentile interval is seeded and reproducible. Returns N/A fields with a
    reason when there are fewer than two clusters.
    """
    if not 0 < confidence < 1 or n_boot < 1:
        raise ValueError("confidence must be in (0,1) and n_boot positive")
    ids = sorted(set(a) & set(b))
    result: dict[str, Any] = {"n": len(ids), "diff": None, "ci_low": None, "ci_high": None,
                              "n_clusters": 0, "n_boot": n_boot, "seed": seed, "confidence": confidence,
                              "method": "cluster percentile bootstrap", "na_reason": None}
    if not ids:
        result["na_reason"] = "no identical cases answered by both candidates"
        return result
    by_cluster: dict[str, list[float]] = {}
    for cid in ids:
        by_cluster.setdefault(clusters.get(cid, cid), []).append(a[cid] - b[cid])
    sums = [(sum(v), len(v)) for _, v in sorted(by_cluster.items())]
    result["n_clusters"] = len(sums)
    result["diff"] = sum(s for s, _ in sums) / len(ids)
    if len(sums) < 2:
        result["na_reason"] = "fewer than two clusters; interval undefined"
        return result
    rng = random.Random(seed)
    reps = []
    for _ in range(n_boot):
        total = count = 0
        for _ in sums:
            s, n = sums[rng.randrange(len(sums))]
            total += s
            count += n
        reps.append(total / count)
    tail = (1 - confidence) / 2
    result["ci_low"] = percentile(reps, tail)
    result["ci_high"] = percentile(reps, 1 - tail)
    return result


# --------------------------------------------------------------------------- per-case helpers
def _get(outcomes: OutcomeMap, case_id: str, task: str) -> Outcome:
    try:
        return outcomes[(case_id, task)]
    except KeyError:
        raise ValueError(f"missing outcome for {case_id}/{task}; every call needs an outcome") from None


def _answered(outcomes: OutcomeMap, case_id: str, task: str) -> Outcome | None:
    out = _get(outcomes, case_id, task)
    return out if out.status == "ok" else None


def _level_gap(pred: str, want: str) -> int:
    return abs(PRIORITY_INDEX[pred] - PRIORITY_INDEX[want])


def _na_reason(outs: Iterable[Outcome], what: str) -> str:
    outs = list(outs)
    if outs and all(o.status == "unsupported" for o in outs):
        return f"{what}: unsupported by this candidate (N/A, not approximated)"
    return f"{what}: no valid answers"


def metric_vector(metric: str, cases: list[dict[str, Any]], outcomes: OutcomeMap) -> dict[str, float]:
    """Per-case 0/1 values for the paired bootstrap, keyed by case id.

    Accuracy metrics include a case only when it was answered. The strict forms
    include every eligible case and score a non-answer as 0.
    """
    vec: dict[str, float] = {}
    for case in cases:
        g = gold(case)
        if g is None or case["cohort"] not in GRADED_COHORTS:
            continue
        cid = case["case_id"]
        if metric == "event_type_accuracy":
            o = _answered(outcomes, cid, "event_type")
            if o:
                vec[cid] = float(o.value == g["event_type"])
        elif metric == "page_now_accuracy":
            o = _answered(outcomes, cid, "page_now")
            if o:
                vec[cid] = float(o.value == g["page_now"])
        elif metric == "priority_accuracy":
            o = _answered(outcomes, cid, "priority")
            if o:
                vec[cid] = float(o.value == g["priority"])
        elif metric == "must_page_recall_strict":
            if g["page_now"] is True:
                o = _answered(outcomes, cid, "page_now")
                vec[cid] = float(bool(o and o.value is True))
        elif metric == "spoof_escalation_kept_strict":
            if case["cohort"] == "B_prime" and g["page_now"] is True:
                o = _answered(outcomes, cid, "page_now")
                vec[cid] = float(bool(o and o.value is True))
        else:
            raise ValueError(f"unknown metric {metric!r}")
    return vec


PAIRED_METRICS = ("event_type_accuracy", "page_now_accuracy", "priority_accuracy",
                  "must_page_recall_strict", "spoof_escalation_kept_strict")


# --------------------------------------------------------------------------- cohort cells
def _pair_metrics(cohort_cases: list[dict[str, Any]], all_cases: dict[str, dict[str, Any]],
                  outcomes: OutcomeMap) -> dict[str, Any]:
    """Paired inversion accuracy for B children against their A parent.

    A pair is correct when the page_now answer is right on *both* members, so a
    model that ignores context fails every label-flip pair. Pairs with a
    non-answered member are excluded from the denominator and counted as
    incomplete (they are visible, not hidden).
    """
    total = flips_total = ok = flips_ok = incomplete = 0
    for child in cohort_cases:
        parent = all_cases.get(child.get("parent_case_id") or "")
        g_child = gold(child)
        g_parent = gold(parent) if parent else None
        if parent is None or g_child is None or g_parent is None:
            incomplete += 1
            continue
        oc = _answered(outcomes, child["case_id"], "page_now")
        op = _answered(outcomes, parent["case_id"], "page_now")
        if oc is None or op is None:
            incomplete += 1
            continue
        good = oc.value == g_child["page_now"] and op.value == g_parent["page_now"]
        total += 1
        ok += good
        if child.get("pair_relation") == "label_flip":
            flips_total += 1
            flips_ok += good
    return {"paired_inversion": proportion(ok, total, "no complete pairs"),
            "paired_inversion_flip_only": proportion(flips_ok, flips_total, "no complete label-flip pairs"),
            "incomplete_pairs": incomplete}


def cohort_metrics(cases: list[dict[str, Any]], outcomes: OutcomeMap,
                   all_cases: dict[str, dict[str, Any]], cohort: str) -> dict[str, Any]:
    """Every cell for one column group (a cohort, or ``pooled``) of one candidate arm.

    ``cases`` must already be the test cases of that column. ``cohort`` is one of
    A, B, B_prime, C, D or ``pooled`` (A+B+B'+C, the graded cases only).
    """
    calls = [(c["case_id"], t) for c in cases for t in TASKS]
    outs = [_get(outcomes, cid, t) for cid, t in calls]
    count = {s: sum(o.status == s for o in outs) for s in STATUSES}
    attempted = count["ok"] + count["schema_failure"] + count["exception"]
    per_task = {}
    for t in TASKS:
        to = [o for o in outs if o.task == t]
        per_task[t] = {s: sum(o.status == s for o in to) for s in STATUSES} | {"calls": len(to)}
    cell: dict[str, Any] = {
        "n_cases": len(cases),
        "coverage": proportion(count["ok"], len(outs), "no calls"),
        "schema_failure_rate": proportion(count["schema_failure"], attempted, "no attempted calls"),
        "exception_rate": proportion(count["exception"], attempted, "no attempted calls"),
        "unsupported_rate": proportion(count["unsupported"], len(outs), "no calls"),
        "per_task_status": per_task,
    }
    graded = [c for c in cases if cohort != "D" and gold(c) is not None and c["cohort"] in GRADED_COHORTS]
    gold_na = ("cohort D has no gold (needs_adjudication); no accuracy is computed" if cohort == "D"
               else "no graded cases")

    def accuracy(task: str, label: str) -> Proportion:
        if not graded:
            return not_applicable(gold_na)
        right = n = 0
        for c in graded:
            o = _answered(outcomes, c["case_id"], task)
            if o:
                n += 1
                right += o.value == gold(c)[task]
        return proportion(right, n, _na_reason((_get(outcomes, c["case_id"], task) for c in graded), label))

    cell["event_type_accuracy"] = accuracy("event_type", "event_type")
    cell["page_now_accuracy"] = accuracy("page_now", "page_now")
    cell["priority_accuracy"] = accuracy("priority", "priority")

    # priority within one level, and ordinal MAE (in P levels)
    gaps = []
    for c in graded:
        o = _answered(outcomes, c["case_id"], "priority")
        if o:
            gaps.append(_level_gap(o.value, gold(c)["priority"]))
    cell["priority_within_one"] = (proportion(sum(g <= 1 for g in gaps), len(gaps), "no valid priority answers")
                                   if graded else not_applicable(gold_na))
    cell["priority_mae_levels"] = {
        "mean": (sum(gaps) / len(gaps)) if gaps else None, "n": len(gaps),
        "na_reason": None if gaps else (gold_na if not graded else "no valid priority answers"),
        "note": "mean absolute gap in ordinal P levels (P1=1 .. P4=4); no interval computed"}

    # must-page recall (answered and strict) and false-page rate
    positives = [c for c in graded if gold(c)["page_now"] is True]
    negatives = [c for c in graded if gold(c)["page_now"] is False]
    pos_ans = [(c, _answered(outcomes, c["case_id"], "page_now")) for c in positives]
    neg_ans = [(c, _answered(outcomes, c["case_id"], "page_now")) for c in negatives]
    if graded:
        cell["must_page_recall"] = proportion(sum(1 for _, o in pos_ans if o and o.value is True),
                                              sum(1 for _, o in pos_ans if o), "no answered must-page cases")
        cell["must_page_recall_strict"] = proportion(
            sum(1 for _, o in pos_ans if o and o.value is True), len(positives),
            "no must-page cases in this cohort")
        cell["false_page_rate"] = proportion(sum(1 for _, o in neg_ans if o and o.value is True),
                                             sum(1 for _, o in neg_ans if o), "no answered not-page cases")
    else:
        for k in ("must_page_recall", "must_page_recall_strict", "false_page_rate"):
            cell[k] = not_applicable(gold_na)

    # cohort-specific cells
    if cohort == "B":
        cell.update(_pair_metrics(graded, all_cases, outcomes))
    else:
        for k in ("paired_inversion", "paired_inversion_flip_only"):
            cell[k] = not_applicable(NOT_DEFINED)
    if cohort == "B_prime":
        kept = [(c, _answered(outcomes, c["case_id"], "page_now")) for c in positives]
        cell["spoof_escalation_kept"] = proportion(sum(1 for _, o in kept if o and o.value is True),
                                                   sum(1 for _, o in kept if o), "no answered B' cases")
        cell["spoof_escalation_kept_strict"] = proportion(
            sum(1 for _, o in kept if o and o.value is True), len(kept), "no escalating B' cases")
    else:
        for k in ("spoof_escalation_kept", "spoof_escalation_kept_strict"):
            cell[k] = not_applicable(NOT_DEFINED)

    if cohort == "D":
        cell["provisional_agreement"] = _provisional_agreement(cases, outcomes)
        cell["abstention"] = not_applicable(
            "the adapter interface has no abstain output; abstention cannot be observed (needs a WS8 contract "
            "change, and it is not inferred from a probability near 0.5)")
    return cell


def _provisional_agreement(cases: list[dict[str, Any]], outcomes: OutcomeMap) -> dict[str, Any]:
    """Agreement with provisional labels for cohort D, only if any are present.

    The generator ships none (``expected`` is null), so this is N/A today. The
    name is deliberate: this is agreement with provisional labels, not accuracy.
    """
    labelled = [c for c in cases if c.get("expected")]
    if not labelled:
        return {"na_reason": "no provisional labels present (cohort D is needs_adjudication); "
                             "nothing is invented", "per_task": {}}
    per_task = {}
    for t in TASKS:
        right = n = 0
        for c in labelled:
            o = _answered(outcomes, c["case_id"], t)
            if o:
                n += 1
                right += o.value == gold(c)[t]
        per_task[t] = proportion(right, n, "no answered calls").to_dict()
    return {"na_reason": None, "per_task": per_task, "note": "agreement with provisional labels, not accuracy"}


def build_cohort_matrix(test_cases: list[dict[str, Any]], outcomes: OutcomeMap) -> dict[str, dict[str, Any]]:
    """Column groups A, B, B_prime, C, D and pooled for one candidate arm."""
    by_id = {c["case_id"]: c for c in test_cases}
    matrix: dict[str, dict[str, Any]] = {}
    for cohort in ("A", "B", "B_prime", "C", "D"):
        matrix[cohort] = cohort_metrics([c for c in test_cases if c["cohort"] == cohort],
                                        outcomes, by_id, cohort)
    matrix["pooled"] = cohort_metrics([c for c in test_cases if c["cohort"] in GRADED_COHORTS],
                                      outcomes, by_id, "pooled")
    return matrix


# --------------------------------------------------------------------------- consequential errors
def consequential_errors(test_cases: list[dict[str, Any]], outcomes: OutcomeMap) -> dict[str, Any]:
    """Case ids of missed pages and improper suppressions (PRACTICAL_EVAL_V2 4a).

    A missed page on a B or B' case is an improper suppression (the model let a
    change window or a payload claim retain an event that should have escalated).
    A missed page elsewhere is a missed must-page. Non-answered must-page cases
    are listed separately: they are neither correct nor a wrong answer.
    """
    missed, improper, unanswered = [], [], []
    for c in test_cases:
        g = gold(c)
        if g is None or c["cohort"] not in GRADED_COHORTS or g["page_now"] is not True:
            continue
        o = _get(outcomes, c["case_id"], "page_now")
        if o.status != "ok":
            unanswered.append({"case_id": c["case_id"], "cohort": c["cohort"], "status": o.status})
        elif o.value is False:
            (improper if c["cohort"] in ("B", "B_prime") else missed).append(
                {"case_id": c["case_id"], "cohort": c["cohort"]})
    return {"missed_must_page": {"count": len(missed), "cases": missed},
            "improper_suppression": {"count": len(improper), "cases": improper},
            "unanswered_must_page": {"count": len(unanswered), "cases": unanswered}}


# --------------------------------------------------------------------------- cost
def case_costs(case: dict[str, Any], outcomes: OutcomeMap, matrix: dict[str, float]) -> dict[str, Any]:
    """Cost of one graded case under the (placeholder) cost matrix, per task.

    Strict: a non-answer is charged the worst wrong answer for that case and
    task, so a candidate cannot lower its cost by failing to answer.
    """
    g = gold(case)
    assert g is not None
    suppressible = case["cohort"] in ("B", "B_prime")
    miss_key = "improper_suppression" if suppressible else "missed_must_page"
    parts: dict[str, float] = {}
    worst: dict[str, float] = {}

    ev = _get(outcomes, case["case_id"], "event_type")
    worst["event_type"] = matrix["wrong_queue"]
    parts["event_type"] = (0 if ev.status == "ok" and ev.value == g["event_type"] else matrix["wrong_queue"])

    pg = _get(outcomes, case["case_id"], "page_now")
    if g["page_now"]:
        worst["page_now"] = matrix[miss_key]
        parts["page_now"] = 0 if pg.status == "ok" and pg.value is True else matrix[miss_key]
    else:
        worst["page_now"] = matrix["false_page"]
        parts["page_now"] = 0 if pg.status == "ok" and pg.value is False else matrix["false_page"]

    pr = _get(outcomes, case["case_id"], "priority")
    worst["priority"] = matrix["priority_off_by_two_plus"]
    if pr.status == "ok":
        gap = _level_gap(pr.value, g["priority"])
        parts["priority"] = 0 if gap == 0 else (matrix["priority_off_by_one"] if gap == 1
                                                else matrix["priority_off_by_two_plus"])
    else:
        parts["priority"] = matrix["priority_off_by_two_plus"]
    return {"parts": parts, "worst": worst}


def cost_weighted(test_cases: list[dict[str, Any]], outcomes: OutcomeMap, matrix: dict[str, float],
                  cohorts: tuple[str, ...] = ("A", "B")) -> dict[str, Any]:
    """Mean cost per case, and cost as a fraction of the worst possible, for ``cohorts``.

    N/A when any of the three tasks is wholly unsupported: a total over a
    partial set of tasks would be a silent approximation.
    """
    chosen = [c for c in test_cases if c["cohort"] in cohorts and gold(c) is not None]
    result: dict[str, Any] = {"cohorts": list(cohorts), "n_cases": len(chosen), "matrix_status": "PLACEHOLDER (D13)",
                              "total_cost": None, "mean_cost_per_case": None, "worst_possible_total": None,
                              "normalized_error": None, "by_task": {}, "na_reason": None}
    if not chosen:
        result["na_reason"] = "no graded cases in the chosen cohorts"
        return result
    for t in TASKS:
        task_outs = [_get(outcomes, c["case_id"], t) for c in chosen]
        if all(o.status == "unsupported" for o in task_outs):
            result["na_reason"] = f"task {t} is unsupported; a total over the other tasks would be an approximation"
            return result
    totals = {t: 0.0 for t in TASKS}
    worsts = {t: 0.0 for t in TASKS}
    for c in chosen:
        cc = case_costs(c, outcomes, matrix)
        for t in TASKS:
            totals[t] += cc["parts"][t]
            worsts[t] += cc["worst"][t]
    result["by_task"] = {t: {"cost": totals[t], "worst": worsts[t]} for t in TASKS}
    result["total_cost"] = sum(totals.values())
    result["worst_possible_total"] = sum(worsts.values())
    result["mean_cost_per_case"] = result["total_cost"] / len(chosen)
    result["normalized_error"] = (result["total_cost"] / result["worst_possible_total"]
                                  if result["worst_possible_total"] else None)
    return result


def worst_failures(test_cases: list[dict[str, Any]], outcomes: OutcomeMap, matrix: dict[str, float],
                   limit: int = 3) -> list[dict[str, Any]]:
    """The costliest (case, task) failures, ties broken by case id then task order."""
    rows = []
    for c in test_cases:
        g = gold(c)
        if g is None or c["cohort"] not in GRADED_COHORTS:
            continue
        cc = case_costs(c, outcomes, matrix)
        for t in TASKS:
            if cc["parts"][t] > 0:
                o = _get(outcomes, c["case_id"], t)
                rows.append({"case_id": c["case_id"], "cohort": c["cohort"], "task": t, "cost": cc["parts"][t],
                             "gold": g[t], "predicted": o.value if o.status == "ok" else None,
                             "status": o.status})
    rows.sort(key=lambda r: (-r["cost"], r["case_id"], TASKS.index(r["task"])))
    return rows[:limit]


# --------------------------------------------------------------------------- calibration
def reliability_bins(probabilities: list[float], labels: list[bool], bins: int = 10) -> list[dict[str, Any]]:
    """Per-bin counts using exactly the binning of ``evaluation.metrics.ece``:
    confidence of the predicted class, ``max(p, 1-p)``."""
    if len(probabilities) != len(labels) or bins < 2:
        raise ValueError("Expected paired probabilities/labels and at least two bins")
    rows = []
    for i in range(bins):
        members = [(p, y) for p, y in zip(probabilities, labels)
                   if min(int(max(0, min(1, max(p, 1 - p))) * bins), bins - 1) == i]
        rows.append({"bin": i, "low": i / bins, "high": (i + 1) / bins, "n": len(members),
                     "mean_confidence": (sum(max(p, 1 - p) for p, _ in members) / len(members)) if members else None,
                     "accuracy": (sum((p >= 0.5) == y for p, y in members) / len(members)) if members else None})
    return rows


def calibration_summary(test_cases: list[dict[str, Any]], outcomes: OutcomeMap) -> dict[str, Any]:
    """Pooled Brier and ECE with bin counts over graded A/B/B'/C cases.

    Only probabilities whose source is ``model`` count. A hard label or a
    generated claim is not a calibrated probability, so such an arm is N/A.
    Cohort D is excluded (no gold) and no per-cohort ECE is offered.
    """
    pairs, sources, ineligible = [], set(), 0
    graded = [c for c in test_cases if c["cohort"] in GRADED_COHORTS and gold(c) is not None]
    for c in graded:
        o = _get(outcomes, c["case_id"], "page_now")
        if o.status != "ok":
            continue
        sources.add(o.probability_source)
        if o.probability_source in CALIBRATABLE_SOURCES and o.probability is not None:
            pairs.append((o.probability, bool(gold(c)["page_now"])))
        else:
            ineligible += 1
    summary: dict[str, Any] = {"scope": "pooled A+B+B'+C graded cases; cohort D excluded; no per-cohort ECE",
                               "n": len(pairs), "n_graded": len(graded), "n_ineligible": ineligible,
                               "probability_sources": sorted(s or "none" for s in sources),
                               "brier": None, "ece": None, "bins": [], "na_reason": None, "warning": None}
    if not pairs:
        summary["na_reason"] = ("no calibrated probabilities: the probability source is "
                                f"{sorted(s or 'none' for s in sources) or 'absent'}, not 'model'")
        return summary
    probs = [p for p, _ in pairs]
    labels = [y for _, y in pairs]
    summary["brier"] = brier(probs, labels)
    summary["ece"] = ece(probs, labels)
    summary["bins"] = reliability_bins(probs, labels)
    summary["warning"] = "ECE is a diagnostic and unstable below a few hundred cases" if len(pairs) < 300 else None
    return summary


# --------------------------------------------------------------------------- latency
def latency_summary(samples: list[tuple[str, float]]) -> dict[str, Any]:
    """p50/p95 over timed (task, milliseconds) samples; N/A when none were taken."""
    values = [ms for _, ms in samples]
    out: dict[str, Any] = {"n": len(values), "p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95),
                           "by_task": {}, "na_reason": None if values else "no timing samples (not measured)"}
    for t in TASKS:
        tv = [ms for task, ms in samples if task == t]
        out["by_task"][t] = {"n": len(tv), "p50_ms": percentile(tv, 0.5), "p95_ms": percentile(tv, 0.95)}
    return out
