"""Contract, split, and calibration checks that require no model download."""

import math

import pytest

from data.synthetic_generator import generate
from evaluation.metrics import brier, ece, percentile
from models.base import DecisionCase, DecisionResult, SchemaFailure
from training.calibrate import fit_temperature, temperature_scale


def test_grouped_splits_and_reproducibility():
    first = generate(1000, 42)
    assert first == generate(1000, 42)
    assert sum(len(rows) for rows in first.values()) == 1000
    groups = [{case.pair_id for case in rows} for rows in first.values()]
    assert all(a.isdisjoint(b) for index, a in enumerate(groups) for b in groups[index + 1:])
    assert all(len([case for case in rows if case.pair_id == row.pair_id]) == 2
               for rows in first.values() for row in rows)


def test_output_contract_rejects_bad_values():
    case = DecisionCase("a", "g", "state", "question", "choice", "one", ("one", "two"))
    with pytest.raises(SchemaFailure):
        DecisionResult(choice="other").validate(case)
    with pytest.raises(SchemaFailure):
        DecisionResult(choice="one", choice_probs={"one": 0.7, "two": 0.7}).validate(case)
    noul = DecisionCase("b", "g", "state", "question", "noul", True)
    with pytest.raises(SchemaFailure):
        DecisionResult(noul_prob=math.nan).validate(noul)


def test_calibration_metrics_and_temperature():
    assert brier([0.0, 1.0], [False, True]) == 0
    assert ece([0.0, 1.0], [False, True]) == 0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    temp = fit_temperature([0.1, 0.9], [False, True])
    assert 0.5 <= temp <= 5
    assert temperature_scale(0.5, temp) == pytest.approx(0.5)
