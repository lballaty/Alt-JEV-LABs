"""Runner tests use a deterministic fake to check accounting, not model quality."""

from pathlib import Path

from data.synthetic_generator import generate
from evaluation.benchmark_runner import assess
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
