"""Loss functions with explicit target scales."""


def brier_loss(probabilities, targets):
    """Binary Brier loss, averaged across a batch of tensors."""
    return ((probabilities - targets) ** 2).mean()


def multitask_loss(kind, choice_logits, score_logits, noul_logits, target):
    import torch

    if kind == "choice":
        return torch.nn.functional.cross_entropy(choice_logits, target.long())
    if kind == "score":
        # The score target is normalized from 0–100 to 0–1.
        return torch.nn.functional.mse_loss(torch.sigmoid(score_logits[:, 0]), target.float() / 100.0)
    if kind == "noul":
        return brier_loss(torch.sigmoid(noul_logits[:, 0]), target.float())
    raise ValueError(f"Unknown task kind: {kind}")
