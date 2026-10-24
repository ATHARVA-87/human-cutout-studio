#!/usr/bin/env python3
"""Train U-Net and save only the validation-Dice-best checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

# Support `python scripts/train.py` without requiring an editable installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from segmentation.data import SegmentationDataset
from segmentation.models import UNet, UNetConfig
from segmentation.training import train


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/train.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--checkpoint", type=Path, default=Path("backend/weights/model.pth"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    train_data = SegmentationDataset(args.data_root, "train", augment=True)
    validation_data = SegmentationDataset(args.data_root, "validation")
    pin_memory = torch.cuda.is_available()
    train_loader = DataLoader(
        train_data, batch_size=config["batch_size"], shuffle=True, num_workers=config["num_workers"], pin_memory=pin_memory
    )
    validation_loader = DataLoader(
        validation_data, batch_size=config["batch_size"], shuffle=False, num_workers=config["num_workers"], pin_memory=pin_memory
    )
    model = UNet(UNetConfig(base_channels=config["base_channels"], dropout=config["dropout"]))
    print(f"device={'cuda' if torch.cuda.is_available() else 'cpu'} train={len(train_data)} validation={len(validation_data)}")
    print(train(model, train_loader, validation_loader, config, args.checkpoint))


if __name__ == "__main__":
    main()
