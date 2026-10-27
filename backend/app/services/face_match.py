"""
Identity verification: does a submitted selfie match one of an employee's
5 enrolled reference embeddings?

Uses best-of-5 comparison — compare against all 5 references, take the
highest similarity score. More forgiving of angle/lighting variance in
any single reference photo (see our planning discussion on why 5 photos
beats 1).
"""
import logging

import numpy as np

from app.config import settings
from app.services.face_detect import cosine_similarity, get_embedding

logger = logging.getLogger("face_match")


def enroll_embeddings(reference_images: list[bytes]) -> list[list[float]]:
    """
    Convert up to 5 reference selfies into stored embeddings (as plain
    lists, for SQL Server storage — numpy arrays aren't directly serializable).
    Skips any image where no face is detected, logs a warning.
    """
    embeddings = []
    for i, image_bytes in enumerate(reference_images):
        emb = get_embedding(image_bytes)
        if emb is None:
            logger.warning("No face detected in reference image %d — skipped", i)
            continue
        embeddings.append(emb.tolist())
    return embeddings


def verify_identity(
    submitted_image: bytes, enrolled_embeddings: list[list[float]]
) -> tuple[str, float]:
    """
    Compare a submitted selfie against an employee's enrolled embeddings.

    Returns (verdict, best_score) where verdict is one of:
      "verified"    - best_score >= face_match_pass_threshold
      "uncertain"   - between uncertain and pass thresholds -> flag for human review
      "rejected"    - below uncertain threshold, or no face detected at all
    """
    submitted_emb = get_embedding(submitted_image)
    if submitted_emb is None:
        return "rejected", 0.0

    if not enrolled_embeddings:
        logger.warning("No enrolled embeddings available for comparison")
        return "rejected", 0.0

    scores = [
        cosine_similarity(submitted_emb, np.array(ref))
        for ref in enrolled_embeddings
    ]
    best_score = max(scores)

    if best_score >= settings.face_match_pass_threshold:
        return "verified", best_score
    elif best_score >= settings.face_match_uncertain_threshold:
        return "uncertain", best_score
    else:
        return "rejected", best_score