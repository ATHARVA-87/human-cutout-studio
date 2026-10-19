"""Person segmentation with the trained U-Net checkpoint."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

from segmentation.checkpoints import CheckpointSpec, build_model, parse_checkpoint

OVERLAY_COLOR = np.array([38, 198, 218], dtype=np.float32)


@dataclass(frozen=True)
class SegmentationResult:
    mask: Image.Image  # black/white, same size as the input
    cutout: Image.Image  # RGBA: the person with a soft-edged transparent background
    overlay: Image.Image  # input with the person tinted, for a quick visual check
    foreground_fraction: float
    model_version: str


class SegmentationService:
    """Loads the model once at startup. The checkpoint itself describes its architecture and preprocessing."""

    def __init__(self, checkpoint_path: Path, threads: int = 1) -> None:
        self.checkpoint_path = checkpoint_path
        self.threads = threads
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: torch.nn.Module | None = None
        self.spec: CheckpointSpec | None = None
        self.model_version = "unloaded"
        # Requests run in a thread pool; the lock lets only one image use the model at a time,
        # which keeps memory predictable on a small server or a 6 GB GPU.
        self._lock = threading.Lock()

    def load(self) -> None:
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Model checkpoint is missing: {self.checkpoint_path}")
        torch.set_num_threads(self.threads)
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
        probability = self._probability_map(original)  # float32, values 0..1, same size as `original`

        # Hard mask for the downloadable mask.png and the foreground percentage.
        binary = probability >= self.spec.preprocessing.output_threshold
        mask = Image.fromarray(binary.astype(np.uint8) * 255)  # 2-D uint8 -> grayscale "L"

        # Soft alpha for the cutout: a slight blur feathers the edge so it blends into new backgrounds.
        feather = max(1, round(min(original.size) / 400))
        alpha = mask.filter(ImageFilter.GaussianBlur(feather))
        cutout = original.copy()
        cutout.putalpha(alpha)

        pixels = np.asarray(original, dtype=np.float32)
        pixels[binary] = 0.55 * pixels[binary] + 0.45 * OVERLAY_COLOR
        overlay = Image.fromarray(pixels.astype(np.uint8))
        return SegmentationResult(mask, cutout, overlay, float(binary.mean()), self.model_version)

    def _probability_map(self, original: Image.Image) -> np.ndarray:
        """Run the U-Net at its training size, then resize the probabilities back to the original size."""
        spec = self.spec.preprocessing
        resized, crop_box = self._resize_for_model(original, spec)
        pixels = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(pixels.transpose(2, 0, 1))  # HWC -> CHW
        mean = torch.tensor(spec.mean).view(3, 1, 1)
        std = torch.tensor(spec.std).view(3, 1, 1)
        tensor = ((tensor - mean) / std).unsqueeze(0).to(self.device)
        with self._lock, torch.no_grad():
            logits = self.model(tensor)
        small = Image.fromarray(torch.sigmoid(logits)[0, 0].cpu().numpy())  # float32 -> mode "F"
        if crop_box is not None:
            small = small.crop(crop_box)
        # Bilinear resizing of probabilities (not of the 0/255 mask) gives smooth, non-blocky edges.
        return np.asarray(small.resize(original.size, Image.Resampling.BILINEAR), dtype=np.float32)

    @staticmethod
    def _resize_for_model(image: Image.Image, spec) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
        """Resize as the checkpoint says: 'stretch' to the input size, or 'letterbox' (keep aspect, pad)."""
        target_width, target_height = spec.input_width, spec.input_height
        if spec.resize_strategy == "stretch":
            return image.resize((target_width, target_height), Image.Resampling.BILINEAR), None
        scale = min(target_width / image.width, target_height / image.height)
        scaled_width, scaled_height = round(image.width * scale), round(image.height * scale)
        left, top = (target_width - scaled_width) // 2, (target_height - scaled_height) // 2
        canvas = Image.new("RGB", (target_width, target_height))
        canvas.paste(image.resize((scaled_width, scaled_height), Image.Resampling.BILINEAR), (left, top))
        return canvas, (left, top, left + scaled_width, top + scaled_height)
