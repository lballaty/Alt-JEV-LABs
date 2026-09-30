"""Adapter for the independently maintained Laya-MLX inference runtime."""

from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable, SchemaFailure


class LayaMLX(BaseDecisionModel):
    name = "laya"

    def __init__(self, checkpoint: str, score_levels: list[str]):
        if len(score_levels) != 5:
            raise ValueError("This benchmark maps exactly five ordinal score levels to 0–100")
        try:
            import laya_mlx
        except ImportError as exc:
            raise ModelUnavailable("Install the Apple extra on an Apple Silicon Mac") from exc
        self.checkpoint = checkpoint
        self.score_levels = score_levels
        try:
            self.agent = laya_mlx.load(checkpoint, dtype="float16")
        except Exception as exc:
            raise ModelUnavailable(f"Could not load Laya checkpoint {checkpoint}: {exc}") from exc

    def evaluate(self, case: DecisionCase) -> DecisionResult:
        definition: dict = {"type": case.kind, "instructions": case.question}
        if case.kind == "choice":
            definition["criteria"] = list(case.options)
        elif case.kind == "score":
            definition["criteria"] = self.score_levels
        try:
            response = self.agent.predict(case.state, {"decision": definition})
            answer = response["answers"]["decision"]
        except (KeyError, TypeError) as exc:
            raise SchemaFailure(f"Unexpected Laya result structure: {exc}") from exc
        if case.kind == "choice":
            try:
                probs = answer.get("probabilities")
                mapped = {str(k): float(v) for k, v in probs.items()} if isinstance(probs, dict) else None
                result = DecisionResult(choice=str(answer["choice"]), choice_probs=mapped)
            except (KeyError, ValueError, TypeError) as exc:
                raise SchemaFailure(f"Invalid Laya choice: {exc}") from exc
        elif case.kind == "score":
            try:
                result = DecisionResult(score=float(answer["score"]) * 25.0)
            except (KeyError, ValueError, TypeError) as exc:
                raise SchemaFailure(f"Invalid Laya score: {exc}") from exc
        else:
            try:
                result = DecisionResult(noul_prob=float(answer["noul"]))
            except (KeyError, ValueError, TypeError) as exc:
                raise SchemaFailure(f"Invalid Laya noul: {exc}") from exc
        return result.validate(case)
