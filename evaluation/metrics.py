"""Pure functions for classification, calibration and latency statistics."""

import math
import statistics


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be in [0,1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def brier(probabilities: list[float], labels: list[bool]) -> float | None:
    if not probabilities:
        return None
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels have different lengths")
    return statistics.mean((p - int(y)) ** 2 for p, y in zip(probabilities, labels))


def ece(probabilities: list[float], labels: list[bool], bins: int = 10) -> float | None:
    """Binary ECE using confidence of the predicted class, not P(true) alone."""
    if not probabilities:
        return None
    if len(probabilities) != len(labels) or bins < 2:
        raise ValueError("Expected paired probabilities/labels and at least two bins")
    total = len(labels)
    error = 0.0
    for index in range(bins):
        rows = [(p, y) for p, y in zip(probabilities, labels)
                if min(int(max(0, min(1, max(p, 1 - p))) * bins), bins - 1) == index]
        if not rows:
            continue
        confidence = statistics.mean(max(p, 1 - p) for p, _ in rows)
        accuracy = statistics.mean((p >= 0.5) == y for p, y in rows)
        error += len(rows) / total * abs(accuracy - confidence)
    return error


def finite_probability(value: float) -> bool:
    return math.isfinite(value) and 0 <= value <= 1
