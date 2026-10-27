"""
Passive anti-spoofing guard for WhatsApp selfie images.

Important:
A single still image cannot provide cryptographic/strong liveness proof.

This module is therefore a risk signal, not a standalone biometric
liveness certification.

Background faces are ignored when determining whether the selfie contains
an unexpected number of people.

The primary/foreground face is used for:
- face-size calculation
- liveness checks
"""

from io import BytesIO
import logging

import numpy as np
from PIL import Image

from app.config import settings
from app.services.face_detect import (
    analyze_faces,
    get_primary_face,
    get_significant_faces,
)

logger = logging.getLogger("liveness")


def _laplacian_variance(gray: np.ndarray) -> float:
    """
    Dependency-free sharpness estimate using a 3x3 Laplacian.
    """

    p = np.pad(
        gray.astype(np.float32),
        1,
        mode="edge",
    )

    lap = (
        p[:-2, 1:-1]
        + p[2:, 1:-1]
        + p[1:-1, :-2]
        + p[1:-1, 2:]
        - 4 * p[1:-1, 1:-1]
    )

    return float(lap.var())


def check_passive_liveness(
    image_bytes: bytes,
) -> tuple[str, list[str], dict]:

    if not settings.liveness_enabled:
        return "disabled", [], {}

    try:
        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")

        arr = np.asarray(image)

    except Exception:
        return (
            "suspicious",
            ["image_decode_failed"],
            {},
        )

    height, width = arr.shape[:2]

    # ---------------------------------------------------------
    # Detect faces
    # ---------------------------------------------------------

    faces = analyze_faces(image_bytes)

    if not faces:
        return (
            "suspicious",
            ["no_face_detected"],
            {
                "face_count": 0,
            },
        )

    # ---------------------------------------------------------
    # Select primary/foreground face
    # ---------------------------------------------------------

    primary_face = get_primary_face(faces)

    if primary_face is None:
        return (
            "suspicious",
            ["no_primary_face"],
            {
                "face_count": len(faces),
            },
        )

    # ---------------------------------------------------------
    # Count only significant/foreground faces
    #
    # Background people are ignored.
    # ---------------------------------------------------------

    significant_faces = get_significant_faces(faces)

    significant_face_count = len(
        significant_faces
    )

    # IMPORTANT:
    #
    # Do NOT use:
    #
    #     len(faces) != 1
    #
    # because a normal street selfie can contain people
    # in the background.
    #
    # Instead, only significant foreground faces matter.

    if significant_face_count > 1:
        return (
            "suspicious",
            ["expected_one_primary_face"],
            {
                "detected_face_count": len(faces),
                "significant_face_count": significant_face_count,
            },
        )

    # ---------------------------------------------------------
    # Primary face bounding box
    # ---------------------------------------------------------

    x1, y1, x2, y2 = [
        int(v)
        for v in primary_face.bbox
    ]

    face_width = max(
        0,
        min(width, x2) - max(0, x1),
    )

    face_height = max(
        0,
        min(height, y2) - max(0, y1),
    )

    face_ratio = (
        face_width * face_height
    ) / float(
        width * height or 1
    )

    # ---------------------------------------------------------
    # Image quality
    # ---------------------------------------------------------

    gray = np.asarray(
        image.convert("L"),
        dtype=np.float32,
    )

    sharpness = _laplacian_variance(
        gray
    )

    brightness = float(
        gray.mean()
    )

    issues: list[str] = []

    # ---------------------------------------------------------
    # Face size
    # ---------------------------------------------------------

    if (
        face_ratio
        < settings.liveness_min_face_ratio
    ):
        issues.append(
            "face_too_small"
        )

    # ---------------------------------------------------------
    # Sharpness
    # ---------------------------------------------------------

    if (
        sharpness
        < settings.liveness_min_sharpness
    ):
        issues.append(
            "image_too_blurry"
        )

    # ---------------------------------------------------------
    # Lighting
    # ---------------------------------------------------------

    if (
        brightness < 25
        or brightness > 245
    ):
        issues.append(
            "extreme_lighting"
        )

    # ---------------------------------------------------------
    # Final liveness result
    # ---------------------------------------------------------

    status = (
        "passed"
        if not issues
        else "suspicious"
    )

    metrics = {
        "face_ratio": round(
            face_ratio,
            4,
        ),
        "sharpness": round(
            sharpness,
            2,
        ),
        "brightness": round(
            brightness,
            2,
        ),

        # Total faces detected by InsightFace.
        "detected_face_count": len(
            faces
        ),

        # Faces considered significant/foreground.
        "significant_face_count": significant_face_count,

        # The primary face is the employee/selfie face.
        "primary_face_selected": True,
    }

    logger.info(
        "Passive liveness=%s metrics=%s issues=%s",
        status,
        metrics,
        issues,
    )

    return (
        status,
        issues,
        metrics,
    )
