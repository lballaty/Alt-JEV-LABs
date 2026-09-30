"""Write a comparison table without replacing missing measurements with zero."""

import json
from pathlib import Path


def display(value, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def write_report(results: dict, destination: Path, raw_destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_destination.parent.mkdir(parents=True, exist_ok=True)
    raw_destination.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Decision model benchmark",
        "",
        "Synthetic fixture results measure this generated dataset only. They do not establish real-world policy accuracy or determinism.",
        "",
        f"- Dataset: {results['dataset']} ({results['test_cases']} held-out cases)",
        f"- Platform: {results['platform']}",
        f"- Python: {results['python']}",
        f"- Iterations per model: {results['iterations']}, warm-up calls: {results['warmup']}",
        "",
        "| Model | Status | P50 ms | P95 ms | Choice accuracy | Score MAE | Noul accuracy | Brier | ECE | Paired inversion | Schema failure | Exception | Coverage |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in results["models"].items():
        line = [
            name, item["status"], display(item.get("p50_ms")), display(item.get("p95_ms")),
            display(item.get("choice_accuracy")), display(item.get("score_mae")),
            display(item.get("noul_accuracy")), display(item.get("brier")),
            display(item.get("ece")), display(item.get("pair_accuracy")),
            display(item.get("schema_failure_rate")), display(item.get("exception_rate")),
            display(item.get("coverage")),
        ]
        lines.append("| " + " | ".join(line) + " |")
    lines += ["", "## Interpretation", ""]
    for name, item in results["models"].items():
        lines.append(f"- **{name}:** {item.get('note', 'No additional note.')}")
    lines += ["", "Schema failures are malformed/out-of-range outputs. Exceptions and unavailable models are separate. "
              "BM25 hard labels and generated LLM probability claims are not calibrated probabilities.",
              "", "See docs/EVALUATION.md for validity limits and the measurement protocol.", ""]
    destination.write_text("\n".join(lines), encoding="utf-8")
