#!/usr/bin/env python3
"""Load the checkpoint in a new Python process and perform one inference."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

# Support `python scripts/verify_checkpoint.py` without requiring an editable installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from segmentation.checkpoints import build_model, parse_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=Path("backend/weights/model.pth"))
    args = parser.parse_args()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    spec = parse_checkpoint(checkpoint)
    model = build_model(spec)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    size = (spec.preprocessing.input_height, spec.preprocessing.input_width)
    with torch.no_grad():
        logits = model(torch.zeros(1, 3, *size))
    if logits.shape != (1, 1, *size):
        raise ValueError(f"Unexpected output shape {tuple(logits.shape)}")
    print(f"verified checkpoint: architecture={spec.architecture} epoch={spec.epoch} val_dice={spec.best_validation_dice:.4f} output={tuple(logits.shape)}")


if __name__ == "__main__":
    main()
