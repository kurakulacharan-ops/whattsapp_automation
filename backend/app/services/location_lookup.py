"""Offline district containment. No geocoding API, network, or Redis dependency."""
import gzip
import json
import logging
import math
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
DATA_PATH = Path(__file__).resolve().parents[1] / "data/boundaries/india-districts.geojson.gz"
DATASET_ID = "geoBoundaries-IND-ADM2-76128533"
# Conservative review band, not an allowed travel radius.
BOUNDARY_REVIEW_METERS = 100.0


def _ring_contains(lon, lat, ring):
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > lat) != (y2 > lat):
            if lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
        previous = current
    return inside


def _near_ring(lon, lat, ring):
    # Local equirectangular projection is adequate for a 100 m review band in India.
    sx = 111320 * math.cos(math.radians(lat))
    sy = 111320
    previous = ring[-1]
    for current in ring:
        ax, ay = (previous[0] - lon) * sx, (previous[1] - lat) * sy
        bx, by = (current[0] - lon) * sx, (current[1] - lat) * sy
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = max(0, min(1, -(ax * dx + ay * dy) / length2)) if length2 else 0
        if (ax + t * dx) ** 2 + (ay + t * dy) ** 2 <= BOUNDARY_REVIEW_METERS ** 2:
            return True
        previous = current
    return False


@lru_cache(maxsize=1)
def _districts():
    with gzip.open(DATA_PATH, "rt", encoding="utf-8") as source:
        features = json.load(source)["features"]
    districts = []
    for feature in features:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        if geometry["type"] not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Unsupported district geometry")
        for polygon in polygons:
            outer = polygon[0]
            bounds = (min(p[0] for p in outer), min(p[1] for p in outer), max(p[0] for p in outer), max(p[1] for p in outer))
            districts.append((feature["properties"], polygon, bounds))
    return districts


def lookup_district(lat, lon):
    base = {"city": None, "district": None, "district_id": None, "dataset_id": DATASET_ID, "match_level": "district"}
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return {**base, "status": "invalid_coordinates"}
    try:
        matches = {}
        margin_y = BOUNDARY_REVIEW_METERS / 111320
        margin_x = margin_y / max(0.01, math.cos(math.radians(lat)))
        for properties, polygon, (xmin, ymin, xmax, ymax) in _districts():
            if not xmin - margin_x <= lon <= xmax + margin_x or not ymin - margin_y <= lat <= ymax + margin_y:
                continue
            if any(_near_ring(lon, lat, ring) for ring in polygon):
                return {**base, "status": "boundary_uncertain"}
            if _ring_contains(lon, lat, polygon[0]) and not any(_ring_contains(lon, lat, hole) for hole in polygon[1:]):
                matches[properties["shapeID"]] = properties["shapeName"]
        if len(matches) != 1:
            return {**base, "status": "ambiguous" if matches else "outside_coverage"}
        district_id, name = next(iter(matches.items()))
        return {**base, "district": name, "district_id": district_id, "place": f"{name} district, India", "status": "resolved"}
    except (OSError, ValueError, KeyError, TypeError):
        logger.exception("Local district dataset unavailable")
        return {**base, "status": "dataset_unavailable"}


async def resolve_location(lat: float, lon: float) -> dict:
    return lookup_district(lat, lon)


def same_district(actual: dict, assigned: dict) -> bool | None:
    if actual.get("status") != "resolved" or assigned.get("status") != "resolved":
        return None
    if not actual.get("district_id") or not assigned.get("district_id") or actual.get("dataset_id") != assigned.get("dataset_id"):
        return None
    return actual["district_id"] == assigned["district_id"]
