"""Shared builders for the WS4 tests: tiny hand-made cases, outcome maps and stub candidates.

The stubs are deterministic test doubles, not models. Nothing computed from them
is a result. Hand-made cases are written so expected values can be worked out on
paper in the tests.
"""

from __future__ import annotations

from typing import Any

from evaluation.v2_data import PRIORITY_ANCHOR
from evaluation.v2_metrics import Outcome
from models.base import BaseDecisionModel, DecisionResult, ModelUnavailable, SchemaFailure

EV = ("security_event", "service_degradation", "data_protection", "policy_deviation", "routine_activity", "telemetry")


def mk_case(cid: str, cohort: str, event_type: str | None = "security_event", page: bool | None = True,
            prio: str | None = "P1", parent: str | None = None, relation: str | None = None,
            pair: str | None = None, split: str = "test") -> dict[str, Any]:
    """A minimal v2 case dict with only the fields the metrics read."""
    graded = event_type is not None
    return {"case_id": cid, "cohort": cohort, "split": split, "pair_id": pair or f"PAIR-{cid}",
            "parent_case_id": parent, "pair_relation": relation,
            "expected": {"choice": event_type, "noul": page, "score": prio} if graded else None}


def mk_outs(cid: str, event: Any = None, page: Any = None, prio: Any = None, prob: float | None = None,
            source: str | None = "model") -> dict[tuple[str, str], Outcome]:
    """Outcomes for one case. Pass an answer for each task, or one of the markers "schema", "exc" or "unsup"
    to make that call a schema_failure, exception or unsupported outcome. Every task needs an outcome."""
    out: dict[tuple[str, str], Outcome] = {}
    for task, value in (("event_type", event), ("page_now", page), ("priority", prio)):
        if value == "schema":
            out[(cid, task)] = Outcome(cid, task, "schema_failure", error="bad")
        elif value == "exc":
            out[(cid, task)] = Outcome(cid, task, "exception", error="boom")
        elif value == "unsup":
            out[(cid, task)] = Outcome(cid, task, "unsupported", error="n/a")
        elif task == "page_now":
            out[(cid, task)] = Outcome(cid, task, "ok", value, probability=prob, probability_source=source)
        else:
            out[(cid, task)] = Outcome(cid, task, "ok", value)
    return out


def perfect_outcomes(cases: list[dict[str, Any]], page_override: dict[str, bool] | None = None,
                     prob: float = 0.9) -> dict[tuple[str, str], Outcome]:
    """Outcomes equal to gold (ungraded cases get fixed arbitrary answers). Test-only construction."""
    outs: dict[tuple[str, str], Outcome] = {}
    for c in cases:
        e = c["expected"]
        page = e["noul"] if e else True
        if page_override and c["case_id"] in page_override:
            page = page_override[c["case_id"]]
        outs.update(mk_outs(c["case_id"], e["choice"] if e else EV[0], page, e["score"] if e else "P4",
                            prob if page else 1 - prob))
    return outs


class StubKeyword(BaseDecisionModel):
    """Deterministic rule stub. Reads only the rendered state text, records every target it was shown."""

    name = "stub-keyword"

    def __init__(self, fail_priority_every: int = 0):
        self.seen_targets: list[Any] = []
        self.calls = 0
        self.fail_priority_every = fail_priority_every

    def evaluate(self, case):
        self.calls += 1
        self.seen_targets.append(case.target)
        text = case.state
        risky = "Failed password" in text or "sudoers" in text
        if case.kind == "choice":
            return DecisionResult(choice=case.options[0] if risky else case.options[1])
        if case.kind == "noul":
            return DecisionResult(noul_prob=0.9 if risky else 0.2, probability_source="model")
        if self.fail_priority_every and self.calls % self.fail_priority_every == 0:
            raise SchemaFailure("stub: out-of-range score")
        return DecisionResult(score=90.0 if risky else 10.0)


class StubAlwaysPage(BaseDecisionModel):
    """Always pages, whatever the input: a deliberately context-blind stub."""

    name = "stub-always-page"

    def evaluate(self, case):
        if case.kind == "choice":
            return DecisionResult(choice=case.options[0])
        if case.kind == "noul":
            return DecisionResult(noul_prob=0.8, probability_source="model")
        return DecisionResult(score=60.0)


class StubFailures(BaseDecisionModel):
    """page_now unsupported (ModelUnavailable), priority raises a backend error, event_type works."""

    name = "stub-failures"

    def evaluate(self, case):
        if case.kind == "choice":
            return DecisionResult(choice=case.options[0])
        if case.kind == "noul":
            raise ModelUnavailable("stub: no page head")
        raise RuntimeError("stub backend failure")


class StubDeclared(StubAlwaysPage):
    """Declares it supports only two tasks; the runner must not call the third."""

    name = "stub-declared"
    v2_supported_tasks = frozenset({"event_type", "page_now"})

    def __init__(self):
        self.kinds_called: list[str] = []

    def evaluate(self, case):
        self.kinds_called.append(case.kind)
        return super().evaluate(case)


class StubHardLabel(BaseDecisionModel):
    """Hard 0/1 page labels: uncalibrated, so calibration must be N/A."""

    name = "stub-hard"

    def evaluate(self, case):
        if case.kind == "choice":
            return DecisionResult(choice=case.options[1])
        if case.kind == "noul":
            return DecisionResult(noul_prob=1.0, probability_source="hard_label_uncalibrated")
        return DecisionResult(score=PRIORITY_ANCHOR["P2"])
