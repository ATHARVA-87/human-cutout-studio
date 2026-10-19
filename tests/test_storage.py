import io

import pytest
from PIL import Image

from backend.app.services.storage import decode_image


def encode(format_name: str, mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (5, 7), 128).save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.mark.parametrize("format_name, mode", [("PNG", "RGBA"), ("JPEG", "RGB")])
def test_jpeg_and_png_decode_to_rgb(format_name: str, mode: str) -> None:
    image = decode_image(encode(format_name, mode))
    assert image.mode == "RGB"
    assert image.size == (5, 7)


@pytest.mark.parametrize("format_name", ["WEBP", "GIF", "BMP"])
def test_other_image_formats_are_rejected_even_if_valid(format_name: str) -> None:
    with pytest.raises(ValueError, match="Invalid or unsupported"):
        decode_image(encode(format_name))


@pytest.mark.parametrize("format_name", ["PNG", "JPEG"])
def test_large_images_are_shrunk_keeping_aspect_ratio(format_name: str) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (4000, 3000), 128).save(buffer, format=format_name)
    image = decode_image(buffer.getvalue(), max_side=1600)
    assert image.size == (1600, 1200)


def test_phone_photo_rotation_tag_is_applied() -> None:
    """Phones save portraits as landscape pixels + EXIF Orientation=6 ('rotate 90°'). We must apply it."""
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation tag
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), 128).save(buffer, format="JPEG", exif=exif)
    assert decode_image(buffer.getvalue()).size == (300, 400)  # upright, as the browser shows it


def test_multi_picture_jpeg_from_phones_is_accepted() -> None:
    """Pillow calls JPEGs with an embedded second image (HDR/portrait photos) 'MPO'."""
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), 100).save(buffer, format="MPO", save_all=True, append_images=[Image.new("RGB", (40, 30), 50)])
    assert Image.open(io.BytesIO(buffer.getvalue())).format == "MPO"
    assert decode_image(buffer.getvalue()).size == (40, 30)


def test_non_image_bytes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid or unsupported"):
        decode_image(b"not an image")
