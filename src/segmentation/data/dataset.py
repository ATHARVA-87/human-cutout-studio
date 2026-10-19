"""Dataset reading only prepared, size-normalized image and mask pairs."""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class SegmentationDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(
        self,
        processed_root: str | Path,
        split: str,
        augment: bool = False,
        mean: tuple[float, float, float] = IMAGENET_MEAN,
        std: tuple[float, float, float] = IMAGENET_STD,
    ) -> None:
        self.root = Path(processed_root)
        self.augment = augment
        self.mean = torch.tensor(mean).view(3, 1, 1)
        self.std = torch.tensor(std).view(3, 1, 1)
        manifest = json.loads((self.root / "splits.json").read_text())
        if split not in manifest["splits"]:
            raise ValueError(f"Unknown split {split!r}")
        self.names: list[str] = manifest["splits"][split]

    def __len__(self) -> int:
        return len(self.names)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        name = self.names[index]
        image = np.asarray(Image.open(self.root / "images" / name).convert("RGB"), dtype=np.float32) / 255.0
        mask = np.asarray(Image.open(self.root / "masks" / name).convert("L"), dtype=np.uint8)
        if self.augment and random.random() < 0.5:
            image, mask = image[:, ::-1].copy(), mask[:, ::-1].copy()
        image_tensor = torch.from_numpy(image.transpose(2, 0, 1))
        image_tensor = (image_tensor - self.mean) / self.std
        mask_tensor = torch.from_numpy((mask > 127).astype(np.float32)).unsqueeze(0)
        return image_tensor, mask_tensor
