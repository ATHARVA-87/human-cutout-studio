#!/usr/bin/env python3
"""Evaluate the saved best checkpoint once on the untouched test split."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from segmentation.checkpoints import build_model, parse_checkpoint
from segmentation.data import SegmentationDataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("backend/weights/model.pth"))
    parser.add_argument("--data-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=2)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    spec = parse_checkpoint(checkpoint)
    model = build_model(spec)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()

    # Evaluation must use the exact normalization recorded in the checkpoint.
    test_set = SegmentationDataset(args.data_root, "test", mean=spec.preprocessing.mean, std=spec.preprocessing.std)
    loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=device.type == "cuda")
    intersection = torch.zeros((), dtype=torch.float64, device=device)
    prediction_pixels = torch.zeros((), dtype=torch.float64, device=device)
    target_pixels = torch.zeros((), dtype=torch.float64, device=device)

    with torch.no_grad():
        for images, masks in tqdm(loader, desc="test evaluation"):
            logits = model(images.to(device))
            predictions = (torch.sigmoid(logits) >= spec.preprocessing.output_threshold).to(torch.float64)
            masks = masks.to(device, dtype=torch.float64)
            intersection += (predictions * masks).sum()
            prediction_pixels += predictions.sum()
            target_pixels += masks.sum()

    dice = (2 * intersection + 1e-6) / (prediction_pixels + target_pixels + 1e-6)
    print(
        f"test_samples={len(test_set)} global_dice={dice.item():.4f} "
        f"threshold={spec.preprocessing.output_threshold:.2f} device={device.type}"
    )


if __name__ == "__main__":
    main()
