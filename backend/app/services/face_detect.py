"""
Face detection and recognition using InsightFace buffalo_l.

Primary-face logic:
- The largest/most prominent face is treated as the employee selfie face.
- Small background faces are ignored.
- Multiple significant/foreground faces can still be detected.
- Face recognition continues to use the primary face.
"""

import logging
from io import BytesIO

import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image

logger = logging.getLogger("face_analysis")

_app: FaceAnalysis | None = None

# A secondary face must be reasonably large compared with the primary face
# before it is considered an unexpected/foreground face.
#
# Example:
# Primary face area = 100,000 px
# Secondary face area = 10,000 px
# Ratio = 0.10 -> background face -> ignored
#
# Secondary face area = 70,000 px
# Ratio = 0.70 -> significant second face -> flagged
SIGNIFICANT_FACE_AREA_RATIO = 0.35


def _get_app() -> FaceAnalysis:
    """Lazy-load InsightFace once and reuse it."""

    global _app

    if _app is None:
        _app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )

        _app.prepare(
            ctx_id=0,
            det_size=(640, 640),
        )

    return _app


def analyze_faces(image_bytes: bytes):
    """
    Detect all faces using InsightFace.

    Returns:
        list of InsightFace Face objects.

    Each Face normally contains:
        .bbox
        .det_score
        .normed_embedding
    """

    try:
        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")

    except Exception as exc:
        logger.warning(
            "Could not decode image for face analysis: %s",
            exc,
        )
        return []

    arr = np.array(image)[:, :, ::-1]

    try:
        return _get_app().get(arr)

    except Exception as exc:
        logger.exception(
            "InsightFace detection failed: %s",
            exc,
        )
        return []


def _face_area(face) -> float:
    """Return bounding-box area for an InsightFace face."""

    try:
        x1, y1, x2, y2 = [
            float(v)
            for v in face.bbox
        ]

        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)

        return width * height

    except Exception:
        return 0.0


def get_primary_face(faces):
    """
    Select the main/foreground face.

    The largest detected face is considered the primary selfie face.

    This is important for WhatsApp selfies where:
        - employee is close to camera
        - other people may appear far in background

    Returns:
        Face object or None.
    """

    if not faces:
        return None

    return max(
        faces,
        key=lambda face: (
            _face_area(face),
            float(getattr(face, "det_score", 0.0)),
        ),
    )


def get_significant_faces(faces):
    """
    Return faces that are large enough to be considered foreground faces.

    The largest face is always included.

    Small background faces are ignored.

    A second face is considered significant only when its area is at least
    SIGNIFICANT_FACE_AREA_RATIO of the primary face area.
    """

    if not faces:
        return []

    primary = get_primary_face(faces)

    if primary is None:
        return []

    primary_area = _face_area(primary)

    if primary_area <= 0:
        return [primary]

    significant = []

    for face in faces:
        area = _face_area(face)

        # Primary face is always significant.
        if face is primary:
            significant.append(face)
            continue

        ratio = area / primary_area

        if ratio >= SIGNIFICANT_FACE_AREA_RATIO:
            significant.append(face)

    return significant


def detect_face(image_bytes: bytes) -> tuple[bool, int]:
    """
    Detect the primary employee face.

    Returns:
        (face_present, significant_face_count)

    Background faces are not counted as unexpected faces.
    """

    faces = analyze_faces(image_bytes)

    if not faces:
        return False, 0

    significant_faces = get_significant_faces(faces)

    return True, len(significant_faces)


def get_embedding(image_bytes: bytes) -> np.ndarray | None:
    """
    Return the embedding of the primary/foreground face.

    The largest face is treated as the employee's selfie face.

    Background faces are ignored.
    """

    faces = analyze_faces(image_bytes)

    if not faces:
        return None

    primary = get_primary_face(faces)

    if primary is None:
        return None

    embedding = getattr(
        primary,
        "normed_embedding",
        None,
    )

    if embedding is None:
        return None

    return np.asarray(
        embedding,
        dtype=np.float32,
    )


def cosine_similarity(
    embedding_a: np.ndarray,
    embedding_b: np.ndarray,
) -> float:
    """
    Calculate cosine similarity.

    Embeddings are L2-normalized by InsightFace,
    so the dot product is sufficient.
    """

    return float(
        np.dot(
            embedding_a,
            embedding_b,
        )
    )
