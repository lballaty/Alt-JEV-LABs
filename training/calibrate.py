"""Temperature fitting on held-out validation predictions only."""

import math


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def temperature_scale(probability: float, temperature: float) -> float:
    """Scale a binary logit; clip only to avoid infinite log odds."""
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    p = min(max(probability, 1e-7), 1 - 1e-7)
    return sigmoid(math.log(p / (1 - p)) / temperature)


def fit_temperature(probabilities: list[float], labels: list[bool]) -> float:
    """Small deterministic grid fit on validation data using Brier loss.

    Callers must save the resulting temperature and apply it unchanged to test.
    The benchmark does not auto-fit on test data.
    """
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("Expected nonempty paired validation predictions and labels")
    candidates = [0.5 + i * 0.05 for i in range(91)]
    return min(candidates, key=lambda t: sum(
        (temperature_scale(p, t) - float(y)) ** 2
        for p, y in zip(probabilities, labels)
    ) / len(labels))
