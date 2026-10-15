import io

import pytest
from PIL import Image

from backend.app.services.storage import LocalStorage


def test_decode_returns_rgb_image() -> None:
    buffer = io.BytesIO()
    Image.new("RGBA", (5, 7), (1, 2, 3, 128)).save(buffer, format="PNG")
    image = LocalStorage.decode(buffer.getvalue())
    assert image.mode == "RGB"
    assert image.size == (5, 7)


def test_decode_rejects_invalid_content() -> None:
    with pytest.raises(ValueError, match="Invalid or unsafe"):
        LocalStorage.decode(b"not an image")
