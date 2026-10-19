import numpy as np
from PIL import Image

from backend.app.services.realism import crop_to_person, match_colors, touches_bottom


def person_cutout(width: int = 100, height: int = 80, box=(30, 20, 60, 80)) -> Image.Image:
    """A red 'person' rectangle on a transparent canvas."""
    cutout = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cutout.paste((200, 40, 40, 255), box)
    return cutout


def test_crop_to_person_removes_empty_border() -> None:
    assert crop_to_person(person_cutout()).size == (30, 60)


def test_touches_bottom_detects_half_body_shots() -> None:
    assert touches_bottom(person_cutout(box=(30, 20, 60, 80))) is True  # reaches the bottom edge
    assert touches_bottom(person_cutout(box=(30, 10, 60, 50))) is False  # whole person visible


def test_match_colors_moves_toward_background_but_keeps_shape() -> None:
    cutout = crop_to_person(person_cutout())
    blue_scene = Image.new("RGB", (64, 64), (40, 60, 200))
    result = match_colors(cutout, blue_scene, strength=0.5)
    assert result.size == cutout.size and result.mode == "RGBA"
    assert result.getchannel("A").tobytes() == cutout.getchannel("A").tobytes()  # alpha untouched
    before, after = np.asarray(cutout)[..., :3].mean(axis=(0, 1)), np.asarray(result)[..., :3].mean(axis=(0, 1))
    assert after[2] > before[2]  # more blue
    assert after[0] < before[0]  # less red
