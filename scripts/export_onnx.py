#!/usr/bin/env python3
"""Convert the trained checkpoint (model.pth) into model.onnx for the web server, and check they agree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import onnxruntime
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from segmentation.checkpoints import build_model, parse_checkpoint  # noqa: E402
from segmentation.export import export_to_onnx  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("backend/weights/model.pth"))
    parser.add_argument("--output", type=Path, default=Path("backend/weights/model.onnx"))
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    spec = parse_checkpoint(checkpoint)
    model = build_model(spec)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    export_to_onnx(model, spec, args.output)

    # Same random input through PyTorch and ONNX Runtime: the outputs must match.
    sample = torch.randn(1, 3, spec.preprocessing.input_height, spec.preprocessing.input_width)
    with torch.no_grad():
        expected = model(sample).numpy()
    session = onnxruntime.InferenceSession(str(args.output), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"image": sample.numpy()})[0]
    difference = float(np.abs(expected - actual).max())
    if difference > 1e-3:
        raise SystemExit(f"ONNX output differs from PyTorch by {difference:.2e}")
    size_mb = args.output.stat().st_size / 1e6
    print(f"wrote {args.output} ({size_mb:.1f} MB); max difference vs PyTorch = {difference:.2e}")


if __name__ == "__main__":
    main()
