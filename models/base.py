"""Shared, deliberately strict model contract.

The benchmark runner owns timing. Adapters return typed values and raise an
explicit exception for invalid backend output. This avoids counting a failed
call as a wrong answer or silently replacing it with a guessed value.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

Kind = Literal["choice", "score", "noul"]


class ModelUnavailable(RuntimeError):
    """A dependency, device or trained checkpoint required by a model is absent."""


class SchemaFailure(ValueError):
    """A backend returned data that does not match the decision contract."""


@dataclass(frozen=True)
class DecisionCase:
    id: str
    pair_id: str
    state: str
    question: str
    kind: Kind
    target: str | float | bool
    options: tuple[str, ...] = ()
    adversarial: bool = False

    @classmethod
    def from_dict(cls, value: dict) -> "DecisionCase":
        kind = value["kind"]
        if kind not in ("choice", "score", "noul"):
            raise ValueError(f"Unknown decision kind: {kind}")
        options = tuple(value.get("options", ()))
        if kind == "choice" and not 1 <= len(options) <= 255:
            raise ValueError("Choice requires 1–255 options")
        return cls(
            id=str(value["id"]), pair_id=str(value["pair_id"]),
            state=str(value["state"]), question=str(value["question"]),
            kind=kind, target=value["target"], options=options,
            adversarial=bool(value.get("adversarial", False)),
        )


@dataclass(frozen=True)
class DecisionResult:
    choice: str | None = None
    choice_probs: dict[str, float] | None = None
    score: float | None = None
    noul_prob: float | None = None
    # An LLM-generated decimal is not inherently calibrated. The runner
    # reports its metrics with that limitation visible in the report.
    probability_source: str = "model"

    def validate(self, case: DecisionCase) -> "DecisionResult":
        if case.kind == "choice":
            if self.choice not in case.options:
                raise SchemaFailure(f"Choice {self.choice!r} is outside allowed options")
            if self.choice_probs is not None:
                if set(self.choice_probs) != set(case.options):
                    raise SchemaFailure("Choice probability keys differ from options")
                if any(not math.isfinite(p) or not 0 <= p <= 1 for p in self.choice_probs.values()):
                    raise SchemaFailure("Choice probability outside [0,1]")
                if abs(sum(self.choice_probs.values()) - 1) > 0.02:
                    raise SchemaFailure("Choice probabilities do not sum to one")
        elif case.kind == "score":
            if self.score is None or not math.isfinite(self.score) or not 0 <= self.score <= 100:
                raise SchemaFailure("Score must be finite and within [0,100]")
        else:
            if self.noul_prob is None or not math.isfinite(self.noul_prob) or not 0 <= self.noul_prob <= 1:
                raise SchemaFailure("Noul probability must be finite and within [0,1]")
        return self


class BaseDecisionModel(ABC):
    name: str

    @abstractmethod
    def evaluate(self, case: DecisionCase) -> DecisionResult:
        """Return one decision, including all device synchronization."""

    def warmup(self, case: DecisionCase) -> None:
        """Prime the exact path used by a timed case."""
        self.evaluate(case)
