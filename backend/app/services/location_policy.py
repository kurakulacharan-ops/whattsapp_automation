"""Pass within assigned range, otherwise require the same city/town."""
import math

from app.services.city_lookup import resolve_city, same_city
from app.services.geofence import check_geofence


DEFAULT_ATTENDANCE_RADIUS_KM = 8.0


async def check_attendance_location(lat, lon, site_lat, site_lon, radius_km=DEFAULT_ATTENDANCE_RADIUS_KM):
    result = {"passed": None, "status": "unavailable", "level": "city", "method": "range_then_city", "distance": None, "radius": radius_km * 1000, "assigned": {}, "actual": {}}
    if not all(math.isfinite(value) for value in (lat, lon, site_lat, site_lon, radius_km)) or not (-90 <= lat <= 90 and -90 <= site_lat <= 90 and -180 <= lon <= 180 and -180 <= site_lon <= 180) or radius_km <= 0:
        return result
    within, distance = check_geofence(lat, lon, site_lat, site_lon, radius_km * 1000)
    result["distance"] = distance
    if within:
        return {**result, "passed": True, "status": "in_range", "method": "radius"}
    # Always resolve assignment GPS, avoiding stale or manually guessed city labels.
    assigned = await resolve_city(site_lat, site_lon)
    if not assigned.get("city"):
        return {**result, "assigned": assigned}
    actual = await resolve_city(lat, lon)
    passed = same_city(actual, assigned)
    return {**result, "assigned": assigned, "actual": actual, "passed": passed,
            "status": "in_area" if passed is True else "out_of_area" if passed is False else "unavailable"}
