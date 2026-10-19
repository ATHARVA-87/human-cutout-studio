"""Person segmentation with the trained U-Net, run by ONNX Runtime.

The network is trained in PyTorch (src/segmentation) and exported to model.onnx by
scripts/export_onnx.py. Serving with ONNX Runtime needs about half the memory of PyTorch, and the
.onnx file carries its own preprocessing settings (input size, normalisation, threshold).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime
from PIL import Image, ImageFilter

OVERLAY_COLOR = (38, 198, 218)


@dataclass(frozen=True)
class Preprocessing:
    """How images must be prepared for this model. Written into model.onnx at export time."""

    input_height: int
    input_width: int
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    resize_strategy: str  # "stretch" or "letterbox"
    output_threshold: float


@dataclass(frozen=True)
class SegmentationResult:
    mask: Image.Image  # black/white, same size as the input
    cutout: Image.Image  # RGBA: the person with a soft-edged transparent background
    overlay: Image.Image  # input with the person tinted, for a quick visual check
    foreground_fraction: float
    model_version: str


class SegmentationService:
    """Loads the model once at startup and segments one image at a time."""

    def __init__(self, model_path: Path, threads: int = 1) -> None:
        self.model_path = model_path
        self.threads = threads
        self.session: onnxruntime.InferenceSession | None = None
        self.preprocessing: Preprocessing | None = None
        self.model_version = "unloaded"
        # Requests run in a thread pool; the lock lets only one image use the model at a time,
        # which keeps memory predictable on a small server.
        self._lock = threading.Lock()

    def load(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model file is missing: {self.model_path}")
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        session = onnxruntime.InferenceSession(str(self.model_path), options, providers=["CPUExecutionProvider"])
        metadata = session.get_modelmeta().custom_metadata_map
        if "preprocessing" not in metadata:
            raise ValueError("model.onnx has no preprocessing metadata; create it with scripts/export_onnx.py")
        self.preprocessing = Preprocessing(**json.loads(metadata["preprocessing"]))
        self.model_version = metadata.get("model_version", "unknown")
        self.session = session

    def predict(self, image: Image.Image) -> SegmentationResult:
        if self.session is None or self.preprocessing is None:
            raise RuntimeError("Segmentation model is not loaded")
        original = image.convert("RGB")
        probability = self._probability_map(original)  # float32, values 0..1, same size as `original`

        # Hard mask for the downloadable mask.png and the foreground percentage.
        binary = probability >= self.preprocessing.output_threshold
        mask = Image.fromarray(binary.astype(np.uint8) * 255)  # 2-D uint8 -> grayscale "L"

        # Soft alpha for the cutout: a slight blur feathers the edge so it blends into new backgrounds.
        feather = max(1, round(min(original.size) / 400))
        alpha = mask.filter(ImageFilter.GaussianBlur(feather))
        cutout = original.copy()
        cutout.putalpha(alpha)

        # Overlay: tint the person cyan (45% colour, 55% photo), leave the background as it is.
        tinted = Image.blend(original, Image.new("RGB", original.size, OVERLAY_COLOR), 0.45)
        overlay = Image.composite(tinted, original, mask)
        return SegmentationResult(mask, cutout, overlay, float(binary.mean()), self.model_version)

    def _probability_map(self, original: Image.Image) -> np.ndarray:
        """Run the U-Net at its training size, then resize the probabilities back to the original size."""
        spec = self.preprocessing
        resized, crop_box = self._resize_for_model(original, spec)
        pixels = np.asarray(resized, dtype=np.float32) / 255.0  # H x W x 3, values 0..1
        pixels = (pixels - np.array(spec.mean, dtype=np.float32)) / np.array(spec.std, dtype=np.float32)
        batch = pixels.transpose(2, 0, 1)[np.newaxis]  # -> 1 x 3 x H x W, the layout the network expects
        with self._lock:
            logits = self.session.run(None, {"image": np.ascontiguousarray(batch)})[0]
        # Sigmoid turns logits into the probability of "person". Clipping avoids exp() overflow warnings.
        probability = 1.0 / (1.0 + np.exp(-np.clip(logits[0, 0], -50, 50)))
        small = Image.fromarray(probability.astype(np.float32))  # float32 -> mode "F"
        if crop_box is not None:
            small = small.crop(crop_box)
        # Bilinear resizing of probabilities (not of the 0/255 mask) gives smooth, non-blocky edges.
        return np.asarray(small.resize(original.size, Image.Resampling.BILINEAR), dtype=np.float32)

    @staticmethod
    def _resize_for_model(image: Image.Image, spec: Preprocessing) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
        """Resize as the model expects: 'stretch' to the input size, or 'letterbox' (keep aspect, pad)."""
        target_width, target_height = spec.input_width, spec.input_height
        if spec.resize_strategy == "stretch":
            return image.resize((target_width, target_height), Image.Resampling.BILINEAR), None
        scale = min(target_width / image.width, target_height / image.height)
        scaled_width, scaled_height = round(image.width * scale), round(image.height * scale)
        left, top = (target_width - scaled_width) // 2, (target_height - scaled_height) // 2
        canvas = Image.new("RGB", (target_width, target_height))
        canvas.paste(image.resize((scaled_width, scaled_height), Image.Resampling.BILINEAR), (left, top))
        return canvas, (left, top, left + scaled_width, top + scaled_height)
