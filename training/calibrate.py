"""Temperature fitting on held-out validation predictions only."""

import argparse
import hashlib
import json
import math
from pathlib import Path


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


def sha256(path: Path) -> str:
    """Stream a file hash so calibration cannot be reused with new weights."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def calibrate_mps(validation: Path, checkpoint: Path, output: Path, backbone: str) -> dict:
    """Fit a Noul temperature on validation, then save it with provenance.

    The MPS adapter loads without a calibration file here to obtain raw
    probabilities. No test examples enter this procedure.
    """
    from data.synthetic_generator import read_cases
    from models.custom_heads_mps import ModernBERTMPS

    cases = [case for case in read_cases(validation) if case.kind == "noul"]
    if not cases:
        raise ValueError("Validation split contains no Noul cases")
    model = ModernBERTMPS(backbone, str(checkpoint))
    probabilities = [model.evaluate(case).noul_prob for case in cases]
    labels = [bool(case.target) for case in cases]
    temperature = fit_temperature(probabilities, labels)
    details = {
        "kind": "binary_temperature",
        "temperature": temperature,
        "backbone": backbone,
        "checkpoint_sha256": sha256(checkpoint),
        "validation_sha256": sha256(validation),
        "validation_noul_count": len(cases),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    return details


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=Path("data/splits/val.jsonl"))
    parser.add_argument("--checkpoint", type=Path, default=Path("artifacts/mps-heads.pt"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/mps-calibration.json"))
    parser.add_argument("--backbone", default="answerdotai/ModernBERT-base")
    args = parser.parse_args()
    print(calibrate_mps(args.validation, args.checkpoint, args.output, args.backbone))
