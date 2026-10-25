#!/usr/bin/env python3
"""Train the comparison baseline: a U-Net whose encoder is a ResNet-34 pretrained on ImageNet.

Same data, split, augmentation (horizontal flip), loss (BCE + soft Dice), optimizer family and
"keep the best validation Dice" rule as our from-scratch U-Net (scripts/train.py). The pretrained
encoder is the only real difference, so the benchmark answers "how much does transfer learning buy?".
This model is NOT used by the web app; it exists only for scripts/benchmark_models.py.

    pip install -e '.[benchmark]'
    python scripts/train_pretrained_baseline.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import segmentation_models_pytorch as smp
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from segmentation.data import SegmentationDataset
from segmentation.training.engine import evaluate, set_seed, soft_dice_loss


def build_baseline() -> nn.Module:
    return smp.Unet(encoder_name="resnet34", encoder_weights="imagenet", in_channels=3, classes=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, default=Path("backend/weights/baseline_resnet34_unet.pth"))
    parser.add_argument("--epochs", type=int, default=20)  # pretrained encoders converge faster than our 40 from scratch
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)  # lower than from scratch: don't wreck the pretrained features
    args = parser.parse_args()

    set_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_loader = DataLoader(
        SegmentationDataset(args.data_root, "train", augment=True), batch_size=args.batch_size, shuffle=True, num_workers=2
    )
    validation_loader = DataLoader(SegmentationDataset(args.data_root, "validation"), batch_size=args.batch_size, num_workers=2)
    model = build_baseline().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-5)
    bce = nn.BCEWithLogitsLoss()
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best = -1.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs + 1):
        model.train()
        losses = []
        for images, masks in tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}", leave=False):
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images)
                loss = bce(logits, masks) + soft_dice_loss(logits, masks)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            losses.append(loss.item())
        validation_loss, validation_dice = evaluate(model, validation_loader, device)
        print(f"epoch={epoch} train_loss={np.mean(losses):.4f} val_loss={validation_loss:.4f} val_dice={validation_dice:.4f}")
        if validation_dice > best:
            best = validation_dice
            torch.save({"state_dict": model.state_dict(), "epoch": epoch, "best_validation_dice": best}, args.output)
    print(f"best validation Dice {best:.4f} -> {args.output}")


if __name__ == "__main__":
    main()
