"""Upload validation and local file storage for generated images.

Files go to `settings.storage_dir` (default `uploads/`) and are served under `/media/...`.
On the free hosting tier this disk is temporary; in a bigger deployment this class would be
swapped for object storage such as Amazon S3 without changing the routes.
"""

from __future__ import annotations

import io
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps

from backend.app.core.config import settings

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
# Pillow reports many phone JPEGs (HDR / portrait photos with an embedded second image) as "MPO".
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG"}
MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class StoredArtifacts:
    original_path: str
    mask_path: str
    overlay_path: str
    cutout_path: str


def decode_image(contents: bytes, max_side: int | None = None) -> Image.Image:
    """Decode bytes into an RGB image, accepting only real JPEG/PNG files of a sane size.

    Images are shrunk so the longest side is at most `max_side` pixels. A 12-megapixel phone photo
    would otherwise need about 1 GB of RAM to process, far over the free server's 512 MB.
    """
    max_side = max_side or settings.max_image_side
    try:
        probe = Image.open(io.BytesIO(contents))
        if probe.format not in ALLOWED_FORMATS:
            raise ValueError(f"Unsupported format {probe.format}")
        probe.verify()  # detects truncated/corrupt files
        opened = Image.open(io.BytesIO(contents))  # verify() consumes the image, so open again
        if opened.width * opened.height > MAX_PIXELS:
            raise ValueError("Image has more than 40 megapixels.")
        opened.draft("RGB", (max_side, max_side))  # JPEG only: decode directly at a smaller size (saves memory)
        # Phones store portraits sideways plus an EXIF "rotate me" tag; apply it so people are upright.
        upright: Image.Image = ImageOps.exif_transpose(opened) or opened  # (None only in in-place mode, unused here)
        image = upright.convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)  # keeps the aspect ratio
        return image
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValueError("Invalid or unsupported image upload.") from error


async def read_image(upload: UploadFile) -> Image.Image:
    """Validate one uploaded file (type, size, real image content) and decode it. Raises HTTP errors."""
    # The browser-reported type is checked first for a clear message; decode_image then checks the
    # actual file bytes, because the content type is chosen by the client and can be faked.
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPG and PNG images are supported.")
    # Read at most limit + 1 bytes: a huge upload is rejected without loading it all into memory.
    contents = await upload.read(settings.max_upload_bytes + 1)
    if not contents or len(contents) > settings.max_upload_bytes:
        raise HTTPException(413, f"Images must be smaller than {settings.max_upload_bytes // (1024 * 1024)} MB.")
    try:
        # Decoding and resizing are CPU work: run them in a worker thread so the server stays responsive.
        return await run_in_threadpool(decode_image, contents)
    except ValueError as error:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "The file is not a valid JPG or PNG image.") from error


def media_url(path: str) -> str:
    """Turn a stored file path into the public URL the browser loads, e.g. /media/<uuid>/mask.png."""
    relative = Path(path).resolve().relative_to(settings.storage_dir.resolve())
    return "/media/" + relative.as_posix()


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.storage_dir

    def _new_folder(self) -> Path:
        # A random UUID folder name: URLs cannot be guessed and two jobs never collide.
        folder = self.root / str(uuid.uuid4())
        folder.mkdir(parents=True, exist_ok=False)
        return folder

    def save_prediction(self, original: Image.Image, mask: Image.Image, cutout: Image.Image, overlay: Image.Image) -> StoredArtifacts:
        folder = self._new_folder()
        paths = {name: folder / f"{name}.png" for name in ("original", "mask", "overlay", "cutout")}
        original.save(paths["original"])
        mask.save(paths["mask"])
        overlay.save(paths["overlay"])
        cutout.save(paths["cutout"])
        return StoredArtifacts(*(str(paths[name]) for name in ("original", "mask", "overlay", "cutout")))

    def save_composition(self, background: Image.Image, cutout: Image.Image) -> tuple[str, str]:
        folder = self._new_folder()
        background_path, cutout_path = folder / "background.jpg", folder / "cutout.png"
        background.save(background_path, quality=90)
        cutout.save(cutout_path)
        return str(background_path), str(cutout_path)


def delete_job_folder(path: str) -> None:
    """Delete the uuid folder that holds one job's files. Refuses anything outside the storage folder."""
    folder = Path(path).resolve().parent
    root = settings.storage_dir.resolve()
    if folder.parent == root and folder.is_dir():  # exactly uploads/<uuid>/, never uploads/ itself
        shutil.rmtree(folder, ignore_errors=True)
