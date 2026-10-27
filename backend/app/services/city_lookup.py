"""Cached city/town lookup for setup and out-of-range attendance only."""
import asyncio
import hashlib
import json
import logging
import math
import os
import uuid

import httpx

from app.redis_queue import get_redis
from app.services.location_match import normalize_location_name

logger = logging.getLogger(__name__)


def city_fields(data):
    address = data.get("address") or {}
    return {
        "city": address.get("city") or address.get("town") or address.get("village") or address.get("municipality"),
        "district": address.get("state_district") or address.get("county"),
        "state": address.get("state"),
        "country_code": address.get("country_code"),
        "place": data.get("display_name"),
        "match_level": "city",
    }


def same_city(actual, assigned):
    # Compare city/town with state and country; district does not control eligibility.
    for key in ("city", "state", "country_code"):
        if not str(actual.get(key) or "").strip() or not str(assigned.get(key) or "").strip():
            return None
    for key in ("city", "state", "country_code"):
        left, right = actual.get(key), assigned.get(key)
        if left and right:
            left, right = normalize_location_name(left), normalize_location_name(right)
            if left != right:
                return False
    return True


async def resolve_city(lat, lon):
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return {}
    url = os.getenv("GEOCODING_URL", "https://nominatim.openstreetmap.org/reverse")
    provider = hashlib.sha256(url.encode()).hexdigest()[:16]
    key = f"city:v1:{provider}:{lat:.7f}:{lon:.7f}"
    gate = "city:provider-gate"
    token = uuid.uuid4().hex
    try:
        async with get_redis() as redis:
            cached = await redis.get(key)
            if cached is not None:
                return json.loads(cached)
            for _ in range(80):
                if await redis.set(gate, token, nx=True, ex=30):
                    break
                await asyncio.sleep(0.25)
            else:
                return {}
            try:
                cached = await redis.get(key)
                if cached is not None:
                    return json.loads(cached)
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        response = await client.get(url, params={
                            "lat": lat, "lon": lon, "format": "jsonv2",
                            "addressdetails": 1, "accept-language": "en", "zoom": 18,
                        }, headers={"User-Agent": "bigV-Attendance/1.0 (GPS area verification)"})
                        response.raise_for_status()
                        result = city_fields(response.json())
                    await redis.set(key, json.dumps(result), ex=2592000 if result.get("city") else 60)
                    return result
                except (httpx.HTTPError, ValueError, TypeError):
                    await redis.set(key, "{}", ex=60)
                    logger.warning("City lookup unavailable; manual review required")
                    return {}
            finally:
                # Release only our lease, preserving at least two seconds between calls.
                await redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],2) end return 0", 1, gate, token)
    except Exception:
        logger.warning("City lookup unavailable; manual review required")
        return {}
