"""Training loop with Dice-monitored checkpointing."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

from segmentation.checkpoints import checkpoint_payload
from segmentation.models import UNet


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def dice_score(logits: torch.Tensor, targets: torch.Tensor, epsilon: float = 1e-6) -> torch.Tensor:
    predictions = (torch.sigmoid(logits) >= 0.5).float()
    intersection = (predictions * targets).sum(dim=(1, 2, 3))
    total = predictions.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    return ((2 * intersection + epsilon) / (total + epsilon)).mean()


def soft_dice_loss(logits: torch.Tensor, targets: torch.Tensor, epsilon: float = 1e-6) -> torch.Tensor:
    probabilities = torch.sigmoid(logits)
    intersection = (probabilities * targets).sum(dim=(1, 2, 3))
    total = probabilities.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    return 1 - ((2 * intersection + epsilon) / (total + epsilon)).mean()


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, float]:
    model.eval()
    bce = nn.BCEWithLogitsLoss()
    losses, dices = [], []
    with torch.no_grad():
        for images, masks in tqdm(loader, desc="validation", leave=False):
            images, masks = images.to(device), masks.to(device)
            logits = model(images)
            losses.append((bce(logits, masks) + soft_dice_loss(logits, masks)).item())
            dices.append(dice_score(logits, masks).item())
    return float(np.mean(losses)), float(np.mean(dices))


def train(
    model: UNet,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    config: dict,
    checkpoint_path: str | Path,
) -> dict[str, float]:
    set_seed(int(config["seed"]))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]))
    bce = nn.BCEWithLogitsLoss()
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_dice = -1.0
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, int(config["epochs"]) + 1):
        model.train()
        running_loss = []
        progress = tqdm(train_loader, desc=f"epoch {epoch}/{config['epochs']}")
        for images, masks in progress:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images)
                loss = bce(logits, masks) + soft_dice_loss(logits, masks)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss.append(loss.item())
            progress.set_postfix(loss=f"{np.mean(running_loss):.4f}")
        validation_loss, validation_dice = evaluate(model, validation_loader, device)
        print(f"epoch={epoch} train_loss={np.mean(running_loss):.4f} val_loss={validation_loss:.4f} val_dice={validation_dice:.4f}")
        if validation_dice > best_dice:
            best_dice = validation_dice
            torch.save(checkpoint_payload(model, config, epoch, best_dice), checkpoint_path)
    return {"best_validation_dice": best_dice}
