#!/usr/bin/env python3
"""Validate paired source files, resize them, and create deterministic splits."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from PIL import Image


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True, help="Directory containing images/ and masks/.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--overwrite", action="store_true", help="Delete an existing processed output before writing.")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    if args.size <= 0 or args.train_fraction <= 0 or args.validation_fraction <= 0 or args.train_fraction + args.validation_fraction >= 1:
        raise ValueError("Require a positive size and train + validation fractions below 1.")
    source_images, source_masks = args.raw_root / "images", args.raw_root / "masks"
    image_names = {path.name for path in source_images.iterdir() if path.is_file()}
    mask_names = {path.name for path in source_masks.iterdir() if path.is_file()}
    paired = sorted(image_names & mask_names)
    if not paired or image_names != mask_names:
        raise ValueError(f"Pairing failed: {len(image_names)} images, {len(mask_names)} masks, {len(paired)} pairs.")
    output_images, output_masks = args.output_root / "images", args.output_root / "masks"
    if args.overwrite and args.output_root.exists():
        import shutil
        shutil.rmtree(args.output_root)
    output_images.mkdir(parents=True, exist_ok=True)
    output_masks.mkdir(parents=True, exist_ok=True)
    original_sizes: Counter[tuple[int, int]] = Counter()
    for name in paired:
        existing_image, existing_mask = output_images / name, output_masks / name
        if existing_image.exists() and existing_mask.exists():
            try:
                with Image.open(existing_image) as image_file, Image.open(existing_mask) as mask_file:
                    image_file.load()
                    mask_file.load()
                    if image_file.size == (args.size, args.size) and mask_file.size == (args.size, args.size):
                        continue
                    raise ValueError(f"Existing output has unexpected dimensions for {name}; rerun with --overwrite.")
            except OSError:
                # An interrupted preparation can leave one invalid partial PNG; rewrite it safely.
                pass
        with Image.open(source_images / name) as image_file, Image.open(source_masks / name) as mask_file:
            if image_file.size != mask_file.size:
                raise ValueError(f"Source size mismatch for {name}: {image_file.size} vs {mask_file.size}")
            original_sizes[image_file.size] += 1
            image = image_file.convert("RGB").resize((args.size, args.size), Image.Resampling.BILINEAR)
            mask = mask_file.convert("L").resize((args.size, args.size), Image.Resampling.NEAREST).point(lambda pixel: 255 if pixel > 127 else 0)
            image.save(output_images / name)
            mask.save(output_masks / name)
    names = paired.copy()
    random.Random(args.seed).shuffle(names)
    train_end = int(len(names) * args.train_fraction)
    validation_end = train_end + int(len(names) * args.validation_fraction)
    manifest = {
        "format_version": 1,
        "source_root": str(args.raw_root.resolve()),
        "preprocessing": {"image_size": args.size, "image_resize": "bilinear", "mask_resize": "nearest", "mask_threshold": 127},
        "seed": args.seed,
        "splits": {"train": names[:train_end], "validation": names[train_end:validation_end], "test": names[validation_end:]},
        "source_summary": {"pairs": len(paired), "unique_source_dimensions": len(original_sizes)},
    }
    (args.output_root / "splits.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(paired)} pairs at {args.size}x{args.size}: train={train_end}, validation={validation_end-train_end}, test={len(names)-validation_end}")


if __name__ == "__main__":
    main()
