"""Image fingerprinting for exact and near-duplicate/reused-photo detection."""
import hashlib
import logging
from io import BytesIO
import imagehash
from PIL import Image, ImageOps

from app.config import settings

logger = logging.getLogger("duplicate_check")


def compute_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def compute_image_hash(image_bytes: bytes) -> imagehash.ImageHash:
    """pHash of the source image; tolerant of common resize/recompression."""
    img = Image.open(BytesIO(image_bytes))
    return imagehash.phash(img)


def compute_normalized_hash(image_bytes: bytes) -> imagehash.ImageHash:
    """pHash after deterministic RGB/grayscale normalization and resizing."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    return imagehash.phash(img.convert("L"))


def image_similarity(existing_hash_str: str, new_hash: imagehash.ImageHash) -> tuple[bool, int]:
    existing_hash = imagehash.hex_to_hash(existing_hash_str)
    distance = new_hash - existing_hash
    return distance <= settings.duplicate_hash_hamming_threshold, distance


def is_duplicate(new_hash: imagehash.ImageHash, existing_hash_str: str) -> tuple[bool, int]:
    return image_similarity(existing_hash_str, new_hash)
