"""Versioned checkpoint contract shared by training, verification, and the API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from torch import nn

from segmentation.models import UNet, UNetConfig

ARCHITECTURE_UNET_V1 = "unet.v1"


@dataclass(frozen=True)
class PreprocessingSpec:
    input_height: int
    input_width: int
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    resize_strategy: str
    output_threshold: float


@dataclass(frozen=True)
class CheckpointSpec:
    format_version: int
    architecture: str
    model_config: dict[str, Any]
    preprocessing: PreprocessingSpec
    epoch: int
    best_validation_dice: float


def _input_size(preprocessing: Mapping[str, Any]) -> tuple[int, int]:
    """Accept old square `image_size` metadata and v2 rectangular `input_size`."""
    value = preprocessing.get("input_size", preprocessing.get("image_size"))
    if isinstance(value, int) and value > 0:
        return value, value
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(item, int) and item > 0 for item in value):
        return value[0], value[1]
    raise ValueError("Checkpoint preprocessing requires a positive image_size or [height, width] input_size.")


def parse_checkpoint(checkpoint: Mapping[str, Any]) -> CheckpointSpec:
    required = {"model_config", "state_dict", "preprocessing", "best_validation_dice", "epoch"}
    missing = required - checkpoint.keys()
    if missing:
        raise ValueError(f"Checkpoint missing keys: {sorted(missing)}")
    preprocessing = checkpoint["preprocessing"]
    if not isinstance(preprocessing, Mapping):
        raise ValueError("Checkpoint preprocessing must be a mapping.")
    height, width = _input_size(preprocessing)
    mean = tuple(preprocessing.get("mean", (0.485, 0.456, 0.406)))
    std = tuple(preprocessing.get("std", (0.229, 0.224, 0.225)))
    if len(mean) != 3 or len(std) != 3:
        raise ValueError("This RGB API requires three normalization mean and std values.")
    strategy = preprocessing.get("resize_strategy", "stretch")
    if strategy not in {"stretch", "letterbox"}:
        raise ValueError(f"Unsupported resize_strategy {strategy!r}; expected 'stretch' or 'letterbox'.")
    threshold = float(preprocessing.get("output_threshold", 0.5))
    if not 0.0 < threshold < 1.0:
        raise ValueError("output_threshold must be between 0 and 1.")
    return CheckpointSpec(
        format_version=int(checkpoint.get("format_version", 1)),
        architecture=str(checkpoint.get("architecture", ARCHITECTURE_UNET_V1)),
        model_config=dict(checkpoint["model_config"]),
        preprocessing=PreprocessingSpec(height, width, tuple(float(x) for x in mean), tuple(float(x) for x in std), strategy, threshold),
        epoch=int(checkpoint["epoch"]),
        best_validation_dice=float(checkpoint["best_validation_dice"]),
    )


def build_model(spec: CheckpointSpec) -> nn.Module:
    """Reconstruct a known architecture from checkpoint metadata.

    Register a new architecture here when its Python implementation is added. Unknown
    architecture IDs deliberately fail instead of silently loading incompatible weights.
    """
    if spec.architecture != ARCHITECTURE_UNET_V1:
        raise ValueError(f"Unsupported model architecture {spec.architecture!r}. Add a registered model factory before deploying it.")
    config = UNetConfig(**spec.model_config)
    if config.in_channels != 3 or config.out_channels != 1:
        raise ValueError("The current image API supports RGB input and a single binary-mask output only.")
    return UNet(config)


def checkpoint_payload(model: UNet, config: Mapping[str, Any], epoch: int, best_validation_dice: float) -> dict[str, Any]:
    """Create v2 metadata while keeping inference independent of training defaults."""
    return {
        "format_version": 2,
        "architecture": ARCHITECTURE_UNET_V1,
        "model_config": model.config.to_dict(),
        "state_dict": model.state_dict(),
        "preprocessing": {
            "input_size": [int(config["image_size"]), int(config["image_size"])],
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "resize_strategy": "stretch",
            "output_threshold": 0.5,
            "mask_threshold": 127,
        },
        "training_config": dict(config),
        "best_validation_dice": best_validation_dice,
        "epoch": epoch,
    }
