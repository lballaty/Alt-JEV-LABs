"""Run the same held-out cases through selected local model adapters."""

import argparse
import importlib.metadata
import platform
import sys
import time
from pathlib import Path

import yaml

from data.synthetic_generator import read_cases, write_splits
from evaluation.metrics import brier, ece, percentile
from evaluation.reporter import write_report
from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable, SchemaFailure

KNOWN_MODELS = ("lexical", "laya", "mps", "generative")


def load_model(name: str, config: dict, train_cases: list[DecisionCase]) -> BaseDecisionModel:
    if name == "lexical":
        from models.lexical_bm25 import LexicalBM25
        return LexicalBM25(train_cases)
    if name == "laya":
        from models.laya_runner import LayaMLX
        return LayaMLX(config["laya_checkpoint"], config["score_levels"])
    if name == "mps":
        from models.custom_heads_mps import ModernBERTMPS
        return ModernBERTMPS(config["mps_backbone"], config["mps_checkpoint"], config["max_length"])
    if name == "generative":
        from models.generative_mlx import GenerativeMLX
        return GenerativeMLX(config["generative_checkpoint"])
    raise ValueError(f"Unknown model: {name}")


def assess(model: BaseDecisionModel, cases: list[DecisionCase],
           iterations: int, warmup: int) -> dict:
    if not cases or iterations < 1 or warmup < 0:
        raise ValueError("Expected cases, positive iterations and nonnegative warm-up")
    outputs: dict[str, DecisionResult] = {}
    failures = {"schema": 0, "exception": 0}
    first_errors: list[str] = []
    for case in cases:
        try:
            outputs[case.id] = model.evaluate(case).validate(case)
        except SchemaFailure as exc:
            failures["schema"] += 1
            if len(first_errors) < 3:
                first_errors.append(f"{case.id}: schema: {exc}")
        except Exception as exc:
            failures["exception"] += 1
            if len(first_errors) < 3:
                first_errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    # Cycle through kinds; each timed iteration is one full synchronous call.
    timing_cases = [case for case in cases if case.id in outputs]
    latencies: list[float] = []
    if timing_cases:
        for index in range(warmup + iterations):
            case = timing_cases[index % len(timing_cases)]
            start = time.perf_counter_ns()
            try:
                model.evaluate(case).validate(case)
            except Exception as exc:
                first_errors.append(f"timing {case.id}: {type(exc).__name__}: {exc}")
                break
            if index >= warmup:
                latencies.append((time.perf_counter_ns() - start) / 1_000_000)
    choices = [(case, outputs[case.id]) for case in cases if case.kind == "choice" and case.id in outputs]
    scores = [(case, outputs[case.id]) for case in cases if case.kind == "score" and case.id in outputs]
    nouls = [(case, outputs[case.id]) for case in cases if case.kind == "noul" and case.id in outputs]
    calibrated = [(case, result) for case, result in nouls
                  if result.probability_source == "model"]
    pairs: dict[str, list[tuple[DecisionCase, DecisionResult]]] = {}
    for case in cases:
        if case.id in outputs and case.kind != "score":
            pairs.setdefault(case.pair_id, []).append((case, outputs[case.id]))
    def correct(case: DecisionCase, result: DecisionResult) -> bool:
        return (result.choice == case.target if case.kind == "choice"
                else (result.noul_prob >= 0.5) == bool(case.target))
    completed_pairs = [items for items in pairs.values() if len(items) == 2]
    return {
        "status": "measured" if len(latencies) == iterations else "partial",
        "p50_ms": percentile(latencies, 0.5), "p95_ms": percentile(latencies, 0.95),
        "choice_accuracy": sum(result.choice == case.target for case, result in choices) / len(choices) if choices else None,
        "score_mae": sum(abs(result.score - float(case.target)) for case, result in scores) / len(scores) if scores else None,
        "noul_accuracy": sum(correct(case, result) for case, result in nouls) / len(nouls) if nouls else None,
        "brier": brier([result.noul_prob for _, result in calibrated],
                       [bool(case.target) for case, _ in calibrated]),
        "ece": ece([result.noul_prob for _, result in calibrated],
                   [bool(case.target) for case, _ in calibrated]),
        "pair_accuracy": sum(all(correct(case, result) for case, result in pair)
                             for pair in completed_pairs) / len(completed_pairs) if completed_pairs else None,
        "schema_failure_rate": failures["schema"] / len(cases),
        "exception_rate": failures["exception"] / len(cases),
        "coverage": len(outputs) / len(cases),
        "timing_samples": len(latencies),
        "first_errors": first_errors[:3],
        "note": (f"{len(outputs)}/{len(cases)} cases returned valid results; "
                 f"{len(latencies)}/{iterations} timing samples. "
                 + ("Brier/ECE excluded uncalibrated hard labels or generated claims. " if len(calibrated) < len(nouls) else "")
                 + ("Examples: " + "; ".join(first_errors[:3]) if first_errors else "")),
    }


def run(config_path: Path, data_dir: Path, names: list[str], iterations: int,
        warmup: int, report: Path, raw: Path) -> dict:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not all((data_dir / f"{name}.jsonl").exists() for name in ("train", "val", "test")):
        write_splits(data_dir, int(config["count"]), int(config["seed"]))
    train = read_cases(data_dir / "train.jsonl")
    test = read_cases(data_dir / "test.jsonl")
    manifest = data_dir / "manifest.json"
    if not manifest.exists():
        raise ValueError("Missing dataset manifest; regenerate splits to establish provenance")
    results = {
        "dataset": manifest.read_text(encoding="utf-8").strip(),
        "test_cases": len(test), "platform": platform.platform(),
        "python": sys.version.split()[0], "iterations": iterations, "warmup": warmup,
        "models": {},
    }
    for name in names:
        try:
            model = load_model(name, config, train)
            item = assess(model, test, iterations, warmup)
            item["checkpoint"] = (config.get({"laya": "laya_checkpoint", "mps": "mps_checkpoint",
                                               "generative": "generative_checkpoint"}.get(name, ""), "train split"))
        except ModelUnavailable as exc:
            item = {"status": "unavailable", "note": str(exc)}
        except Exception as exc:
            item = {"status": "error", "note": f"{type(exc).__name__}: {exc}"}
        results["models"][name] = item
        print(f"{name}: {item['status']} — {item['note']}")
    results["packages"] = {
        name: importlib.metadata.version(name) if importlib.util.find_spec(
            {"laya-mlx": "laya_mlx", "mlx-lm": "mlx_lm", "torch": "torch",
             "transformers": "transformers"}.get(name, name.replace("-", "_"))
        ) else None
        for name in ("laya-mlx", "mlx-lm", "torch", "transformers")
    }
    write_report(results, report, raw)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/benchmark_config.yaml"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/splits"))
    parser.add_argument("--models", default="lexical,laya,mps,generative")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--report", type=Path, default=Path("benchmark_results.md"))
    parser.add_argument("--raw", type=Path, default=Path("artifacts/benchmark_results.json"))
    args = parser.parse_args()
    names = args.models.split(",")
    if any(name not in KNOWN_MODELS for name in names):
        parser.error(f"Choose from {', '.join(KNOWN_MODELS)}")
    run(args.config, args.data_dir, names, args.iterations, args.warmup, args.report, args.raw)
