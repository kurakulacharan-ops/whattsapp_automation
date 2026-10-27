"""
Geofence check — is the OCR'd selfie location within the allowed radius
of the employee's assigned site?

Uses the Haversine formula (great-circle distance between two lat/long
points) — no external library needed, this is just spherical trigonometry.
"""
import math

from app.config import settings

EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_METERS * c


def check_geofence(
    selfie_lat: float,
    selfie_lon: float,
    site_lat: float,
    site_lon: float,
    radius_meters: float | None = None,
) -> tuple[bool, float]:
    """
    Returns (passed, distance_in_meters).
    Uses the person's configured radius, or the application default when omitted.
    """
    distance = haversine_distance_meters(selfie_lat, selfie_lon, site_lat, site_lon)
    allowed_radius = radius_meters if radius_meters is not None else settings.geofence_radius_meters
    passed = distance <= allowed_radius
    return passed, distance
