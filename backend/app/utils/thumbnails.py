"""Thumbnail generation & image resizing with Pillow."""

from io import BytesIO
from PIL import Image

THUMBNAIL_SIZE = (256, 256)
_VECTORIZE_MAX_PX = 512          # max dimension for vectorization
_VECTORIZE_JPEG_QUALITY = 80     # good enough for embeddings


def create_thumbnail(image_bytes: bytes, content_type: str = "image/jpeg") -> bytes:
    """Create a JPEG thumbnail from raw image bytes.

    Returns JPEG bytes regardless of input format.
    """
    img = Image.open(BytesIO(image_bytes))

    # Convert RGBA / palette to RGB for JPEG
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer.read()


def get_image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) of an image."""
    img = Image.open(BytesIO(image_bytes))
    return img.size


def resize_for_vectorization(image_bytes: bytes) -> bytes:
    """Down-scale an image to ≤512 px (longest side) for vectorization.

    Returns JPEG bytes.  If the image is already small enough it is
    re-encoded as JPEG to normalise the format (and usually shrinks it).
    This dramatically reduces the payload sent to the Vision API and
    the network transfer time without losing embedding quality.
    """
    img = Image.open(BytesIO(image_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > _VECTORIZE_MAX_PX:
        img.thumbnail((_VECTORIZE_MAX_PX, _VECTORIZE_MAX_PX), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=_VECTORIZE_JPEG_QUALITY)
    buf.seek(0)
    return buf.read()
