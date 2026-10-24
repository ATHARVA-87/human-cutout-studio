"""Small, explainable steps that make a pasted person fit a new background better.

No extra ML model: just Pillow and NumPy.
1. crop_to_person  - remove the empty transparent area so placement/scaling is about the person.
2. touches_bottom  - detect half-body shots (person cut off by the photo's bottom edge); the editor
                     then keeps them glued to the bottom of the new background instead of floating.
3. match_colors    - nudge the person's brightness and color tint toward the background's
                     (mean/std transfer in LAB color space, at partial strength).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageCms

_SRGB = ImageCms.createProfile("sRGB")
_LAB = ImageCms.createProfile("LAB")
_TO_LAB = ImageCms.buildTransformFromOpenProfiles(_SRGB, _LAB, "RGB", "LAB")
_TO_RGB = ImageCms.buildTransformFromOpenProfiles(_LAB, _SRGB, "LAB", "RGB")


def crop_to_person(cutout: Image.Image) -> Image.Image:
    """Crop an RGBA cutout to the bounding box of its visible (non-transparent) pixels."""
    box = cutout.getchannel("A").point(lambda value: 255 if value > 16 else 0).getbbox()
    return cutout.crop(box) if box else cutout


def touches_bottom(cutout: Image.Image, tolerance: float = 0.02) -> bool:
    """True if the person reaches the bottom 2% of the ORIGINAL (uncropped) photo, e.g. legs cut off."""
    alpha = np.asarray(cutout.getchannel("A"))
    rows = max(1, round(alpha.shape[0] * tolerance))
    return bool((alpha[-rows:] > 128).any())


def _to_lab(image: Image.Image) -> np.ndarray:
    """RGB -> LAB as float32. Pillow stores the a/b channels as signed 8-bit values, so unwrap them."""
    lab = np.asarray(ImageCms.applyTransform(image.convert("RGB"), _TO_LAB), dtype=np.int16)
    lab[..., 1:] = np.where(lab[..., 1:] > 127, lab[..., 1:] - 256, lab[..., 1:])
    return lab.astype(np.float32)


def _from_lab(lab: np.ndarray) -> Image.Image:
    encoded = np.empty(lab.shape, dtype=np.uint8)
    encoded[..., 0] = np.clip(np.round(lab[..., 0]), 0, 255)
    encoded[..., 1:] = (np.clip(np.round(lab[..., 1:]), -128, 127).astype(np.int16) % 256).astype(np.uint8)
    lab_image = Image.frombytes("LAB", (lab.shape[1], lab.shape[0]), encoded.tobytes())
    rgb = ImageCms.applyTransform(lab_image, _TO_RGB)
    if rgb is None:  # only happens in in-place mode, which isn't used here
        raise RuntimeError("Colour conversion failed")
    return rgb


def match_colors(cutout: Image.Image, background: Image.Image, strength: float = 0.5) -> Image.Image:
    """Shift the person's LAB mean/std toward the background's (Reinhard color transfer), blended at `strength`.

    L = lightness, a = green-red, b = blue-yellow. Matching them makes a person shot in warm indoor
    light look less out of place on a cool outdoor background. strength=0.5 goes halfway, because a
    full transfer tends to over-tint skin.
    """
    alpha = cutout.getchannel("A")
    person = _to_lab(cutout)
    visible = np.asarray(alpha) > 128
    if visible.sum() < 50:
        return cutout
    small_background = background.convert("RGB").copy()
    small_background.thumbnail((256, 256))  # statistics do not need full resolution
    scene = _to_lab(small_background).reshape(-1, 3)

    person_mean, person_std = person[visible].mean(axis=0), person[visible].std(axis=0) + 1e-6
    scene_mean, scene_std = scene.mean(axis=0), scene.std(axis=0) + 1e-6
    ratio = np.clip(scene_std / person_std, 0.5, 2.0)  # avoid extreme contrast changes
    transferred = (person - person_mean) * ratio + scene_mean
    blended = person + strength * (transferred - person)

    result = _from_lab(blended)
    result.putalpha(alpha)
    return result
