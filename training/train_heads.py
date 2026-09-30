"""Fine-tune the ModernBERT backbone and its three heads on train only."""

import argparse
from pathlib import Path

from data.synthetic_generator import read_cases
from models.custom_heads_mps import CHOICE_LABELS, build_module
from training.losses import multitask_loss


def train(train_path: Path, output: Path, backbone_id: str, epochs: int, learning_rate: float):
    import torch
    from transformers import AutoTokenizer

    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS is required; this training command does not silently use CPU")
    cases = read_cases(train_path)
    if not cases:
        raise ValueError("Empty train split")
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(backbone_id)
    model = build_module(backbone_id).to("mps").train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    for epoch in range(epochs):
        total = 0.0
        for case in cases:
            encoded = tokenizer(case.state, case.question, max_length=512,
                                truncation=True, return_tensors="pt")
            encoded = {key: value.to("mps") for key, value in encoded.items()}
            logits = model(**encoded)
            target_value = (CHOICE_LABELS.index(case.target) if case.kind == "choice"
                            else float(case.target))
            target = torch.tensor([target_value], device="mps")
            loss = multitask_loss(case.kind, *logits, target)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total += loss.item()
        print(f"epoch={epoch + 1} mean_loss={total / len(cases):.5f}")
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.cpu().state_dict(), "backbone_id": backbone_id,
                "labels": CHOICE_LABELS, "epochs": epochs}, output)
    print(f"saved {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, default=Path("data/splits/train.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/mps-heads.pt"))
    parser.add_argument("--backbone", default="answerdotai/ModernBERT-base")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    args = parser.parse_args()
    train(args.train, args.output, args.backbone, args.epochs, args.learning_rate)
