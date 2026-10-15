"""Shared, checkpoint-driven person segmentation inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from segmentation.checkpoints import CheckpointSpec, build_model, parse_checkpoint


@dataclass(frozen=True)
class SegmentationResult:
    mask: Image.Image
    cutout: Image.Image
    overlay: Image.Image
    foreground_fraction: float
    model_version: str


class SegmentationService:
    """Loads the exact architecture and preprocessing metadata stored in the checkpoint."""

    def __init__(self, checkpoint_path: Path) -> None:
        self.checkpoint_path = checkpoint_path
        self.model: torch.nn.Module | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.spec: CheckpointSpec | None = None
        self.model_version = "unloaded"

    def load(self) -> None:
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Model checkpoint is missing: {self.checkpoint_path}")
        checkpoint = torch.load(self.checkpoint_path, map_location=self.device, weights_only=True)
        spec = parse_checkpoint(checkpoint)
        model = build_model(spec)
        model.load_state_dict(checkpoint["state_dict"])
        self.model = model.to(self.device).eval()
        self.spec = spec
        self.model_version = f"{spec.architecture}-epoch-{spec.epoch}-dice-{spec.best_validation_dice:.4f}"

    def predict(self, image: Image.Image) -> SegmentationResult:
        if self.model is None or self.spec is None:
            raise RuntimeError("Segmentation model is not loaded")
        original = image.convert("RGB")
        width, height = original.size
        preprocessing = self.spec.preprocessing
        resized, restore_box = self._resize_for_model(original, preprocessing)
        pixels = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(pixels.transpose(2, 0, 1))
        mean = torch.tensor(preprocessing.mean).view(3, 1, 1)
        std = torch.tensor(preprocessing.std).view(3, 1, 1)
        tensor = ((tensor - mean) / std).unsqueeze(0).to(self.device)
        with torch.no_grad():
            probability = torch.sigmoid(self.model(tensor))[0, 0].cpu().numpy()
        binary = (probability >= preprocessing.output_threshold).astype(np.uint8) * 255
        small_mask = Image.fromarray(binary, mode="L")
        if restore_box is not None:
            small_mask = small_mask.crop(restore_box)
        mask = small_mask.resize((width, height), Image.Resampling.NEAREST)
        mask_array = np.asarray(mask, dtype=np.uint8)
        original_array = np.asarray(original, dtype=np.uint8)
        overlay_array = original_array.copy()
        overlay_array[mask_array > 127] = (0.55 * overlay_array[mask_array > 127] + 0.45 * np.array([38, 198, 218])).astype(np.uint8)
        cutout = original.copy(); cutout.putalpha(mask)
        return SegmentationResult(mask, cutout, Image.fromarray(overlay_array), float((mask_array > 127).mean()), self.model_version)

    @staticmethod
    def _resize_for_model(image: Image.Image, spec) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
        """Apply checkpoint-selected resize and return the probability crop for restoration."""
        target_width, target_height = spec.input_width, spec.input_height
        if spec.resize_strategy == "stretch":
            return image.resize((target_width, target_height), Image.Resampling.BILINEAR), None
        scale = min(target_width / image.width, target_height / image.height)
        scaled_width, scaled_height = round(image.width * scale), round(image.height * scale)
        left, top = (target_width - scaled_width) // 2, (target_height - scaled_height) // 2
        canvas = Image.new("RGB", (target_width, target_height))
        canvas.paste(image.resize((scaled_width, scaled_height), Image.Resampling.BILINEAR), (left, top))
        return canvas, (left, top, left + scaled_width, top + scaled_height)
