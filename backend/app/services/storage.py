"""Local artifact storage; replaceable with object storage later."""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from backend.app.core.config import settings


@dataclass(frozen=True)
class StoredArtifacts:
    original_path: str
    mask_path: str
    overlay_path: str
    cutout_path: str


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.storage_dir

    def save(self, image: Image.Image, mask: Image.Image, cutout: Image.Image, overlay: Image.Image) -> StoredArtifacts:
        identifier = str(uuid.uuid4())
        target = self.root / identifier
        target.mkdir(parents=True, exist_ok=False)
        original, mask_file, cutout_file, overlay_file = target / "original.png", target / "mask.png", target / "cutout.png", target / "overlay.png"
        image.save(original)
        mask.save(mask_file)
        cutout.save(cutout_file)
        overlay.save(overlay_file)
        return StoredArtifacts(*(str(path) for path in (original, mask_file, overlay_file, cutout_file)))

    def save_composition_inputs(self, background: Image.Image, cutout: Image.Image) -> tuple[str, str]:
        target = self.root / str(uuid.uuid4()); target.mkdir(parents=True, exist_ok=False)
        background_path, cutout_path = target / "background.png", target / "cutout.png"
        background.save(background_path); cutout.save(cutout_path)
        return str(background_path), str(cutout_path)

    @staticmethod
    def decode(contents: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(contents))
            image.verify()
            image = Image.open(io.BytesIO(contents))
            image.load()
            if image.width * image.height > 40_000_000:
                raise ValueError("Image has more than 40 megapixels.")
            return image.convert("RGB")
        except (OSError, ValueError) as error:
            raise ValueError("Invalid or unsafe image upload.") from error
