"""Local MLX-LM JSON baselines with separate prompt and finite-token modes.

Finite mode masks next-token logits to a trie of complete JSON candidates.
This is genuine token-level output restriction, but it is a finite answer set,
not a general JSON Schema grammar. A 0–100 score and 0–1 probability are
quantized to 101 values. The report identifies the mode and its limitations.
"""

import json

from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable, SchemaFailure


class FiniteTokenTrie:
    """A small pure-Python trie of complete candidate token sequences."""

    def __init__(self, sequences: list[list[int]]):
        if not sequences or any(not sequence for sequence in sequences):
            raise ValueError("Expected nonempty candidate token sequences")
        self.root: dict = {}
        self.max_length = max(map(len, sequences))
        for sequence in sequences:
            node = self.root
            for token in sequence:
                node = node.setdefault(int(token), {})
            node[None] = True

    def allowed(self, generated: list[int], eos_ids: set[int]) -> set[int]:
        node = self.root
        for token in generated:
            if token not in node:
                raise SchemaFailure("Generated token sequence left the finite JSON grammar")
            node = node[token]
        allowed = {token for token in node if token is not None}
        if None in node:
            allowed.update(eos_ids)
        if not allowed:
            raise SchemaFailure("Finite JSON grammar has no valid continuation")
        return allowed


def json_candidates(case: DecisionCase) -> list[str]:
    """Enumerate valid complete JSON values for the finite mode."""
    if case.kind == "choice":
        values = [{"choice": option} for option in case.options]
    elif case.kind == "score":
        values = [{"score": number} for number in range(101)]
    else:
        values = [{"noul_prob": round(number / 100, 2)} for number in range(101)]
    return [json.dumps(value, separators=(",", ":"), ensure_ascii=False) for value in values]


class GenerativeMLX(BaseDecisionModel):
    name = "generative"

    def __init__(self, checkpoint: str, max_tokens: int = 80, mode: str = "prompt_json"):
        if mode not in ("prompt_json", "finite_json"):
            raise ValueError("mode must be prompt_json or finite_json")
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise ModelUnavailable("Install mlx-lm on an Apple Silicon Mac") from exc
        self.generate = generate
        self.checkpoint = checkpoint
        self.max_tokens = max_tokens
        self.mode = mode
        self.name = f"generative_{mode}"
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
            kwargs = {}
            if self.mode == "finite_json":
                # The prompt is tokenized here and passed as IDs to mlx-lm.
                # This makes the processor's prompt boundary exact even when
                # the tokenizer adds a beginning-of-sequence token.
                bos = getattr(self.tokenizer, "bos_token", None)
                prompt_ids = self.tokenizer.encode(
                    prompt, add_special_tokens=bos is None or not prompt.startswith(bos)
                )
                candidates = json_candidates(case)
                sequences = [self.tokenizer.encode(text, add_special_tokens=False)
                             for text in candidates]
                for text, sequence in zip(candidates, sequences):
                    if self.tokenizer.decode(sequence) != text:
                        raise ModelUnavailable("Tokenizer cannot round-trip a finite JSON candidate")
                trie = FiniteTokenTrie(sequences)
                eos_ids = getattr(self.tokenizer, "eos_token_ids", None)
                if eos_ids is None:
                    eos = getattr(self.tokenizer, "eos_token_id", None)
                    eos_ids = [eos] if eos is not None else []
                if not eos_ids or self.max_tokens < trie.max_length + 1:
                    raise ModelUnavailable("Finite mode needs an EOS token and enough output tokens")
                import mlx.core as mx

                def mask_to_candidates(tokens, logits):
                    # mlx-lm passes the full prompt and previously sampled
                    # tokens. Synchronization avoids reading stale lazy arrays.
                    mx.eval(tokens)
                    history = tokens.tolist()
                    if history[:len(prompt_ids)] != list(prompt_ids):
                        raise SchemaFailure("MLX-LM token history differs from the supplied prompt")
                    allowed = trie.allowed(history[len(prompt_ids):], set(eos_ids))
                    if max(allowed) >= logits.shape[-1]:
                        raise SchemaFailure("Tokenizer EOS/candidate ID exceeds model vocabulary")
                    permitted = mx.array([token in allowed for token in range(logits.shape[-1])])
                    return mx.where(permitted[None, :], logits, -1e9)

                kwargs["logits_processors"] = [mask_to_candidates]
                prompt = prompt_ids
            output = self.generate(self.model, self.tokenizer, prompt=prompt,
                                   max_tokens=self.max_tokens, verbose=False, **kwargs)
        except (ModelUnavailable, SchemaFailure):
            raise
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
