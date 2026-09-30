"""Nearest-labeled-example BM25 control, intentionally simple.

The retrieval corpus contains train cases only. No probability is returned:
BM25 scores are relevance values, not calibrated posterior probabilities.
"""

import re

from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class LexicalBM25(BaseDecisionModel):
    name = "lexical"

    def __init__(self, examples: list[DecisionCase]):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ModelUnavailable("Install rank-bm25 with uv sync") from exc
        if not examples:
            raise ValueError("BM25 training examples cannot be empty")
        self.examples = examples
        self.by_kind = {
            kind: [case for case in examples if case.kind == kind]
            for kind in ("choice", "score", "noul")
        }
        self.indices = {
            kind: BM25Okapi([tokenize(case.state) for case in cases])
            for kind, cases in self.by_kind.items() if cases
        }

    def evaluate(self, case: DecisionCase) -> DecisionResult:
        examples = self.by_kind[case.kind]
        if not examples:
            raise ModelUnavailable(f"No training examples for {case.kind}")
        scores = self.indices[case.kind].get_scores(tokenize(case.state))
        # Stable tie-breaking matters for reproducibility. It also exposes
        # lexical failures when the correct distinction is a short negation.
        best = examples[max(range(len(scores)), key=lambda index: scores[index])]
        if case.kind == "choice":
            if best.target not in case.options:
                raise ModelUnavailable("Training labels do not match this choice set")
            return DecisionResult(choice=str(best.target)).validate(case)
        if case.kind == "score":
            return DecisionResult(score=float(best.target)).validate(case)
        return DecisionResult(noul_prob=float(best.target),
                              probability_source="hard_label_uncalibrated").validate(case)
