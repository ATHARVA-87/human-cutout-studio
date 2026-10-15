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
    def __init__(self, processed_root: str | Path, split: str, augment: bool = False) -> None:
        self.root = Path(processed_root)
        self.augment = augment
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
        mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
        std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
        image_tensor = (image_tensor - mean) / std
        mask_tensor = torch.from_numpy((mask > 127).astype(np.float32)).unsqueeze(0)
        return image_tensor, mask_tensor

