"""Runner tests use a deterministic fake to check accounting, not model quality."""

from pathlib import Path

import pytest

from data.synthetic_generator import generate, write_splits
from evaluation.benchmark_runner import assess, run
from evaluation.reporter import write_report
from models.base import BaseDecisionModel, DecisionResult, SchemaFailure


class OracleForAccounting(BaseDecisionModel):
    name = "fake"

    def evaluate(self, case):
        if case.id.endswith("-b") and case.kind == "choice":
            raise SchemaFailure("sample malformed output")
        if case.kind == "choice":
            return DecisionResult(choice=case.target)
        if case.kind == "score":
            return DecisionResult(score=float(case.target))
        return DecisionResult(noul_prob=float(case.target))


def test_runner_counts_schema_failures_and_samples():
    cases = generate(1000, 42)["test"]
    result = assess(OracleForAccounting(), cases, iterations=12, warmup=2)
    assert result["status"] == "measured"
    assert result["timing_samples"] == 12
    assert result["schema_failure_rate"] > 0
    assert result["coverage"] < 1
    assert result["score_mae"] == 0
    assert result["brier"] == 0


def test_report_shows_unavailable_instead_of_zero(tmp_path: Path):
    result = {"dataset": "synthetic", "test_cases": 10, "platform": "test",
              "python": "3.12", "iterations": 12, "warmup": 2,
              "models": {"laya": {"status": "unavailable", "note": "Mac required"}}}
    report = tmp_path / "report.md"
    write_report(result, report, tmp_path / "raw.json")
    assert "unavailable" in report.read_text()
    assert "N/A" in report.read_text()


def test_runner_rejects_mutated_split(tmp_path: Path):
    data_dir = tmp_path / "splits"
    write_splits(data_dir, 60, 42)
    with (data_dir / "test.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    config = tmp_path / "config.yaml"
    config.write_text("count: 60\nseed: 42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the dataset manifest"):
        run(config, data_dir, ["lexical"], 1, 0, tmp_path / "out.md", tmp_path / "out.json")
