"""Local MLX-LM generative JSON baseline.

This mode prompts for JSON, then checks the returned object strictly. It does
not implement grammar-constrained token decoding; the report names this mode
prompt_json so its schema failure rate is not misrepresented.
"""

import json

from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable, SchemaFailure


class GenerativeMLX(BaseDecisionModel):
    name = "generative_prompt_json"

    def __init__(self, checkpoint: str, max_tokens: int = 80):
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise ModelUnavailable("Install mlx-lm on an Apple Silicon Mac") from exc
        self.generate = generate
        self.checkpoint = checkpoint
        self.max_tokens = max_tokens
        try:
            self.model, self.tokenizer = load(checkpoint)
        except Exception as exc:
            raise ModelUnavailable(f"Could not load generative checkpoint {checkpoint}: {exc}") from exc

    def evaluate(self, case: DecisionCase) -> DecisionResult:
        field = {"choice": "choice", "score": "score", "noul": "noul_prob"}[case.kind]
        instruction = (
            f"Answer the question using only one JSON object with exactly one key, {field!r}. "
            "For choice, use one of the exact option strings. For score, use a number 0–100. "
            "For noul_prob, use a number 0–1 representing P(true). No prose or Markdown.\n"
            f"Options: {json.dumps(case.options)}\nState: {case.state}\nQuestion: {case.question}"
        )
        messages = [{"role": "user", "content": instruction}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        try:
            output = self.generate(self.model, self.tokenizer, prompt=prompt,
                                   max_tokens=self.max_tokens, verbose=False)
        except Exception as exc:
            raise RuntimeError(f"MLX-LM generation failed: {exc}") from exc
        try:
            value = json.loads(output.strip())
            if not isinstance(value, dict) or set(value) != {field}:
                raise SchemaFailure(f"Expected JSON object containing only {field}")
            raw = value[field]
            if case.kind == "choice":
                if not isinstance(raw, str):
                    raise SchemaFailure("Choice must be a string")
                result = DecisionResult(choice=raw)
            else:
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    raise SchemaFailure("Numeric output must be a JSON number")
                result = (DecisionResult(score=float(raw)) if case.kind == "score" else
                          DecisionResult(noul_prob=float(raw), probability_source="generated_claim"))
            return result.validate(case)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise SchemaFailure(f"Invalid JSON decision: {exc}") from exc
