"""Run candidates on the v2 splits through the existing adapter interface (WS4).

Adapters are the unchanged ``models.base.BaseDecisionModel`` classes. This
runner owns timing and scoring, exactly as in v1. It does not load, install or
download any model; a candidate arrives as an already constructed adapter (or as
an explicit "unavailable" record with the reason).

Per case the runner makes three calls (event_type, page_now, priority); see
``evaluation/v2_data.py`` for the mapping and ``docs/EVALUATION_V2.md`` for what
each adapter would need to be retargeted (WS8, not done here).

Outcome handling, never mixed:
  SchemaFailure                 -> status ``schema_failure`` (output violated the contract)
  ModelUnavailable              -> status ``unsupported`` (the adapter cannot do this task)
  any other Exception           -> status ``exception`` (backend error, not a wrong answer)
  a task not in the adapter's declared ``v2_supported_tasks`` -> ``unsupported`` without a call
"""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from dataclasses import dataclass, field
from typing import Any

from evaluation.v2_data import PAGE_THRESHOLD, TASKS, V2Dataset, gold, level_from_score, to_decision_cases
from evaluation.v2_metrics import Outcome, OutcomeMap
from models.base import BaseDecisionModel, DecisionCase, ModelUnavailable, SchemaFailure
from training.calibrate import fit_temperature, temperature_scale

PACKAGES = ("pyyaml", "rank-bm25", "pytest", "mlx", "mlx-lm", "laya-mlx", "torch", "transformers")

TIMING_METHOD = (
    "time.perf_counter_ns around one complete synchronous model.evaluate(case).validate(case) call, batch size 1, "
    "per (case, task) call on the test split; calls cycle through the answered test calls in case-id/task order; "
    "model load, training and the untimed warm-up calls are excluded; accuracy is scored once per call and timing "
    "repeats do not add accuracy samples. Device synchronization is the adapter's responsibility. "
    "Latency measured off the target Mac is not a target-hardware latency."
)

OPERATIONAL_KEYS = ("offline_verified", "license_ok", "peak_memory_gb", "baseline_other_gb",
                    "memory_pressure_normal", "swap_grew", "false_pages_per_1k_s6", "latency_hardware_is_target")


@dataclass
class CandidateSpec:
    """One row of the comparison: a candidate in one arm.

    ``provenance`` carries what only the caller knows (model_id, revision,
    precision, prompt/template, seed). Missing keys are reported as "not
    recorded", never invented. ``operational`` carries measured or attested
    gate inputs (memory, offline, licence); missing means "not evaluated".
    """

    name: str
    arm: str
    model: BaseDecisionModel | None
    provenance: dict[str, Any] = field(default_factory=dict)
    operational: dict[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None

    @property
    def key(self) -> str:
        return f"{self.name}/{self.arm}"

    def __post_init__(self) -> None:
        unknown = set(self.operational) - set(OPERATIONAL_KEYS)
        if unknown:
            raise ValueError(f"unknown operational keys {sorted(unknown)}; allowed {OPERATIONAL_KEYS}")
        if self.model is None and not self.unavailable_reason:
            raise ValueError("a candidate without a model needs an explicit unavailable_reason")


@dataclass
class CandidateRun:
    spec: CandidateSpec
    status: str                                   # measured | partial | unmeasured_timing | unavailable
    test: OutcomeMap | None = None
    val: OutcomeMap | None = None
    latencies: list[tuple[str, float]] = field(default_factory=list)
    timing: dict[str, Any] = field(default_factory=dict)
    first_errors: list[str] = field(default_factory=list)
    calibration: dict[str, Any] | None = None
    note: str = ""


def collect_environment() -> dict[str, Any]:
    """Software and hardware identity of this host. Nothing personal: no hostname or user."""
    from evaluation.benchmark_runner import hardware_description
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": sys.version.split()[0], "implementation": platform.python_implementation(),
            "platform": platform.platform(), "hardware": hardware_description(),
            "power_mode": "not recorded", "packages": versions,
            "memory_sampling": "not run (needs the target Mac; D11/D12 method is open)"}


def _convert(task: str, case_id: str, result: Any) -> Outcome:
    if task == "event_type":
        return Outcome(case_id, task, "ok", value=result.choice)
    if task == "page_now":
        return Outcome(case_id, task, "ok", value=result.noul_prob >= PAGE_THRESHOLD,
                       probability=result.noul_prob, probability_source=result.probability_source)
    return Outcome(case_id, task, "ok", value=level_from_score(result.score), raw_score=result.score)


def _call(model: BaseDecisionModel, dc: DecisionCase) -> Any:
    return model.evaluate(dc).validate(dc)


def run_split(model: BaseDecisionModel, cases: list[dict[str, Any]], include_signal: bool,
              first_errors: list[str]) -> tuple[OutcomeMap, dict[tuple[str, str], DecisionCase]]:
    """Score one split. Targets are withheld from the adapter (``with_target=False``)."""
    declared = getattr(model, "v2_supported_tasks", None)
    outcomes: OutcomeMap = {}
    calls: dict[tuple[str, str], DecisionCase] = {}
    for case in sorted(cases, key=lambda c: c["case_id"]):
        for task, dc in to_decision_cases(case, with_target=False, include_signal=include_signal).items():
            key = (case["case_id"], task)
            calls[key] = dc
            if declared is not None and task not in declared:
                outcomes[key] = Outcome(case["case_id"], task, "unsupported",
                                        error="task not in the adapter's declared v2_supported_tasks")
                continue
            try:
                outcomes[key] = _convert(task, case["case_id"], _call(model, dc))
            except SchemaFailure as exc:
                outcomes[key] = Outcome(case["case_id"], task, "schema_failure", error=str(exc)[:200])
            except ModelUnavailable as exc:
                outcomes[key] = Outcome(case["case_id"], task, "unsupported", error=str(exc)[:200])
            except Exception as exc:  # backend failure: recorded, never turned into a prediction
                outcomes[key] = Outcome(case["case_id"], task, "exception",
                                        error=f"{type(exc).__name__}: {str(exc)[:200]}")
            if outcomes[key].error and len(first_errors) < 3:
                first_errors.append(f"{case['case_id']}/{task}: {outcomes[key].status}: {outcomes[key].error}")
    return outcomes, calls


def time_calls(model: BaseDecisionModel, outcomes: OutcomeMap, calls: dict[tuple[str, str], DecisionCase],
               iterations: int, warmup: int, clock: Any, first_errors: list[str]) -> tuple[list[tuple[str, float]], str]:
    """Time ``iterations`` calls after ``warmup`` untimed calls. ``clock`` is ``time.perf_counter_ns``."""
    if iterations < 0 or warmup < 0:
        raise ValueError("iterations and warm-up must be nonnegative")
    if iterations == 0:
        return [], "not run (iterations=0)"
    keys = [k for k in sorted(calls, key=lambda k: (k[0], TASKS.index(k[1]))) if outcomes[k].status == "ok"]
    if not keys:
        return [], "not run (no answered calls to time)"
    samples: list[tuple[str, float]] = []
    for i in range(warmup + iterations):
        key = keys[i % len(keys)]
        start = clock()
        try:
            _call(model, calls[key])
        except Exception as exc:
            first_errors.append(f"timing {key[0]}/{key[1]}: {type(exc).__name__}: {str(exc)[:200]}")
            return samples, "partial"
        if i >= warmup:
            samples.append((key[1], (clock() - start) / 1_000_000))
    return samples, "measured"


def run_candidate(spec: CandidateSpec, dataset: V2Dataset, iterations: int = 0, warmup: int = 0,
                  include_signal: bool = True, clock: Any = None) -> CandidateRun:
    """Run one candidate on val (calibration only) and test (the measured split)."""
    if spec.model is None:
        return CandidateRun(spec, "unavailable", note=spec.unavailable_reason or "")
    if clock is None:
        import time
        clock = time.perf_counter_ns
    errors: list[str] = []
    test, test_calls = run_split(spec.model, dataset.test, include_signal, errors)
    val, _ = run_split(spec.model, dataset.val, include_signal, errors)
    samples, timing_status = time_calls(spec.model, test, test_calls, iterations, warmup, clock, errors)
    status = {"measured": "measured", "partial": "partial"}.get(timing_status, "unmeasured_timing")
    return CandidateRun(
        spec, status, test, val, samples,
        {"status": timing_status, "iterations_requested": iterations, "warmup": warmup,
         "samples": len(samples), "method": TIMING_METHOD},
        errors[:3], None, "")


def fit_calibrated_arm(raw: CandidateRun, dataset: V2Dataset, arm: str = "calibrated") -> CandidateRun:
    """Derive the validation-calibrated arm from a raw arm without re-running the model.

    Temperature scaling is fitted on **validation** probabilities only
    (``training.calibrate.fit_temperature``, Brier objective, deterministic
    grid) and applied unchanged to test. Temperature scaling keeps 0.5 fixed, so
    the page decisions equal the raw arm's; only probabilities change. A raw arm
    whose probabilities are not ``model`` probabilities (BM25 hard labels,
    generated claims) cannot be calibrated: the arm is returned as unavailable.
    """
    spec = CandidateSpec(raw.spec.name, arm, raw.spec.model, dict(raw.spec.provenance), dict(raw.spec.operational),
                         raw.spec.unavailable_reason)

    def unavailable(reason: str) -> CandidateRun:
        spec.model, spec.unavailable_reason = None, reason
        return CandidateRun(spec, "unavailable", note=reason)

    if raw.status == "unavailable" or raw.val is None or raw.test is None:
        return unavailable(f"raw arm unavailable: {raw.note}")
    val_by_id = {c["case_id"]: c for c in dataset.val}
    probs: list[float] = []
    labels: list[bool] = []
    for (cid, task), out in sorted(raw.val.items()):
        case = val_by_id[cid]
        g = gold(case)
        if task != "page_now" or g is None or out.status != "ok":
            continue
        if out.probability_source == "model" and out.probability is not None:
            probs.append(out.probability)
            labels.append(bool(g["page_now"]))
    if not probs:
        return unavailable("no validation probabilities from a calibratable source (source must be 'model')")
    temperature = fit_temperature(probs, labels)

    def rescale(outcomes: OutcomeMap) -> OutcomeMap:
        scaled: OutcomeMap = {}
        for key, out in outcomes.items():
            if key[1] == "page_now" and out.status == "ok" and out.probability_source == "model":
                out = Outcome(out.case_id, out.task, out.status, out.value,
                              temperature_scale(out.probability, temperature), "model_temperature_scaled",
                              out.raw_score, out.error)
            scaled[key] = out
        return scaled

    calibrated = CandidateRun(spec, raw.status, rescale(raw.test), rescale(raw.val), list(raw.latencies),
                              dict(raw.timing), list(raw.first_errors),
                              {"method": "temperature scaling of the logit (training.calibrate.fit_temperature)",
                               "temperature": temperature, "fit_split": "val", "fit_n": len(probs),
                               "fit_on_test": False, "objective": "Brier on validation, deterministic grid 0.5-5.0",
                               "decision_threshold": PAGE_THRESHOLD,
                               "note": "0.5 is a fixed point of temperature scaling, so decisions equal the raw arm"},
                              "calibrated arm derived from the raw arm's outputs; the model was not run again")
    return calibrated
