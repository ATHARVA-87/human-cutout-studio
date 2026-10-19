"""Export a trained PyTorch U-Net to ONNX for serving.

Training needs PyTorch; the web server does not. ONNX is a standard file format for trained
networks, and ONNX Runtime runs it with about half the memory of PyTorch. That matters on a free
512 MB server. The preprocessing settings are stored INSIDE the .onnx file, so the server never
has to guess the input size or normalisation.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict
from pathlib import Path

import onnx
import torch
from torch import nn

from segmentation.checkpoints import CheckpointSpec

PREPROCESSING_KEY = "preprocessing"
VERSION_KEY = "model_version"


def model_version(spec: CheckpointSpec) -> str:
    return f"{spec.architecture}-epoch-{spec.epoch}-dice-{spec.best_validation_dice:.4f}"


def export_to_onnx(model: nn.Module, spec: CheckpointSpec, output: Path) -> None:
    """Write `output` (.onnx): a fixed 1x3xHxW float input named 'image', logits output named 'logits'."""
    height, width = spec.preprocessing.input_height, spec.preprocessing.input_width
    output.parent.mkdir(parents=True, exist_ok=True)
    # The U-Net has a size check (`if shapes differ: interpolate`). The exporter warns that this `if` is
    # frozen for the example size. That is fine: the server always resizes images to exactly H x W first.
    warnings.filterwarnings("ignore", category=torch.jit.TracerWarning)
    torch.onnx.export(
        model.eval(),
        torch.zeros(1, 3, height, width),  # example input: ONNX records the graph by running it once
        str(output),
        input_names=["image"],
        output_names=["logits"],
        opset_version=17,
        dynamo=False,  # the classic exporter; newer PyTorch defaults to a different one that needs extra packages
    )
    # Attach the preprocessing contract as metadata so the file is self-describing.
    graph = onnx.load(str(output))
    for key, value in {PREPROCESSING_KEY: json.dumps(asdict(spec.preprocessing)), VERSION_KEY: model_version(spec)}.items():
        entry = graph.metadata_props.add()
        entry.key, entry.value = key, value
    onnx.save(graph, str(output))
