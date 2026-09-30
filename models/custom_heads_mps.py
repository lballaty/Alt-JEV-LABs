"""ModernBERT backbone with task-specific supervised heads on PyTorch MPS."""

import json
from pathlib import Path

from models.base import BaseDecisionModel, DecisionCase, DecisionResult, ModelUnavailable

CHOICE_LABELS = ("security_alert", "schema_mismatch", "telemetry_heartbeat", "audit_log")


def build_module(backbone_id: str):
    """Build at call time so non-Apple hosts can import the project cheaply."""
    import torch
    from transformers import AutoModel

    class DecisionHeads(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = AutoModel.from_pretrained(backbone_id)
            width = self.encoder.config.hidden_size
            self.choice = torch.nn.Linear(width, len(CHOICE_LABELS))
            self.score = torch.nn.Linear(width, 1)
            self.noul = torch.nn.Linear(width, 1)

        def forward(self, input_ids, attention_mask):
            hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            mask = attention_mask.unsqueeze(-1)
            # Padding has no contribution to the mean representation.
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            return self.choice(pooled), self.score(pooled), self.noul(pooled)

    return DecisionHeads()


class ModernBERTMPS(BaseDecisionModel):
    name = "mps_heads"

    def __init__(self, backbone_id: str, checkpoint: str, max_length: int = 512,
                 calibration_path: str | None = None):
        try:
            import torch
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise ModelUnavailable("Install torch and transformers with the Apple extra") from exc
        if not torch.backends.mps.is_available():
            raise ModelUnavailable("PyTorch MPS is not available; CPU fallback is disabled")
        path = Path(checkpoint)
        if not path.is_file():
            raise ModelUnavailable(f"Train the MPS head first: missing {path}")
        self.torch = torch
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(backbone_id)
        self.model = build_module(backbone_id).to("mps")
        state = torch.load(path, map_location="mps", weights_only=True)
        if state.get("backbone_id") != backbone_id or tuple(state.get("labels", ())) != CHOICE_LABELS:
            raise ModelUnavailable("Checkpoint backbone or label order differs from configuration")
        self.model.load_state_dict(state["model"])
        self.model.eval()
        self.noul_temperature = None
        if calibration_path:
            calibration = Path(calibration_path)
            if not calibration.is_file():
                raise ModelUnavailable(f"Missing validation calibration file: {calibration}")
            from training.calibrate import sha256
            values = json.loads(calibration.read_text(encoding="utf-8"))
            if (values.get("kind") != "binary_temperature"
                    or values.get("backbone") != backbone_id
                    or values.get("checkpoint_sha256") != sha256(path)):
                raise ModelUnavailable("Calibration does not match this trained checkpoint")
            temperature = float(values["temperature"])
            if not 0 < temperature <= 10:
                raise ModelUnavailable("Invalid Noul temperature in calibration file")
            self.noul_temperature = temperature

    def evaluate(self, case: DecisionCase) -> DecisionResult:
        if case.kind == "choice" and tuple(case.options) != CHOICE_LABELS:
            raise ModelUnavailable("This MPS head only supports its four trained choice labels")
        inputs = self.tokenizer(case.state, case.question, return_tensors="pt",
                                max_length=self.max_length, truncation=True)
        inputs = {key: value.to("mps") for key, value in inputs.items()}
        with self.torch.inference_mode():
            choice, score, noul = self.model(**inputs)
            if case.kind == "choice":
                probabilities = self.torch.softmax(choice[0], dim=-1).cpu().tolist()
                result = DecisionResult(
                    choice=CHOICE_LABELS[max(range(len(probabilities)), key=probabilities.__getitem__)],
                    choice_probs=dict(zip(CHOICE_LABELS, probabilities)),
                )
            elif case.kind == "score":
                result = DecisionResult(score=float(self.torch.sigmoid(score[0, 0]).item() * 100))
            else:
                probability = float(self.torch.sigmoid(noul[0, 0]).item())
                if self.noul_temperature is not None:
                    from training.calibrate import temperature_scale
                    probability = temperature_scale(probability, self.noul_temperature)
                result = DecisionResult(noul_prob=probability)
        # .item() and .cpu() synchronize MPS, so timing includes inference.
        return result.validate(case)
