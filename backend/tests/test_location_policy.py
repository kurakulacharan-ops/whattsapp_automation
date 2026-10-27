import unittest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from app.services.city_lookup import city_fields, same_city, resolve_city
from app.services.location_policy import check_attendance_location
from app.services.geofence import haversine_distance_meters

AREA = {"city": "Nagpur", "district": "Nagpur", "state": "Maharashtra", "country_code": "in"}


class CityTests(unittest.TestCase):
    def test_locality_does_not_replace_city(self):
        self.assertEqual(city_fields({"address": {**AREA, "suburb": "Dharampeth"}})["city"], "Nagpur")
        self.assertEqual(city_fields({"address": {"town": "Ashti"}})["city"], "Ashti")

    def test_name_and_context(self):
        self.assertTrue(same_city(AREA, {**AREA, "city": "NAGPUR", "district": "Nagpur District"}))
        for key in ("city", "state", "country_code"):
            self.assertFalse(same_city(AREA, {**AREA, key: "different"}))
            self.assertIsNone(same_city(AREA, {**AREA, key: None}))
        self.assertFalse(same_city(AREA, {**AREA, "city": "New Nagpur"}))
        self.assertTrue(same_city(AREA, {**AREA, "district": "Another district"}))
        self.assertTrue(same_city(AREA, {**AREA, "district": None}))


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_eight_km_skips_city_inside_and_checks_city_outside(self):
        with patch("app.services.location_policy.resolve_city", new=AsyncMock(side_effect=[AREA, AREA])) as lookup:
            inside = await check_attendance_location(21.21, 79.0882, 21.1458, 79.0882)
            self.assertTrue(inside["passed"])
            self.assertEqual(inside["radius"], 8000)
            self.assertEqual(inside["status"], "in_range")
            lookup.assert_not_awaited()
            outside = await check_attendance_location(21.23, 79.0882, 21.1458, 79.0882)
            self.assertTrue(outside["passed"])
            self.assertEqual(outside["status"], "in_area")
            self.assertEqual(lookup.await_count, 2)

    async def test_same_point_and_nearby_skip_city_lookup(self):
        with patch("app.services.location_policy.resolve_city", new_callable=AsyncMock) as lookup:
            for lat, lon in [(21.1458, 79.0882), (21.15, 79.09)]:
                result = await check_attendance_location(lat, lon, 21.1458, 79.0882, 5)
                self.assertTrue(result["passed"])
                self.assertEqual(result["status"], "in_range")
            lookup.assert_not_awaited()

    async def test_exact_range_boundary_passes(self):
        radius = haversine_distance_meters(21.2, 79.1, 21.1458, 79.0882) / 1000
        with patch("app.services.location_policy.resolve_city", new_callable=AsyncMock) as lookup:
            result = await check_attendance_location(21.2, 79.1, 21.1458, 79.0882, radius)
            self.assertTrue(result["passed"])
            lookup.assert_not_awaited()

    async def test_outside_range_same_city_passes(self):
        with patch("app.services.location_policy.resolve_city", new=AsyncMock(side_effect=[AREA, AREA])) as lookup:
            result = await check_attendance_location(21.25, 79.1, 21.1458, 79.0882, 1)
            self.assertTrue(result["passed"])
            self.assertEqual(result["status"], "in_area")
            self.assertEqual(lookup.await_count, 2)

    async def test_outside_range_different_city_flags(self):
        with patch("app.services.location_policy.resolve_city", new=AsyncMock(side_effect=[AREA, {**AREA, "city": "Other town"}])):
            result = await check_attendance_location(21.25, 79.1, 21.1458, 79.0882, 1)
            self.assertFalse(result["passed"])
            self.assertEqual(result["status"], "out_of_area")

    async def test_unavailable_city_requires_review(self):
        for answers in ([{}], [AREA, {}]):
            with patch("app.services.location_policy.resolve_city", new=AsyncMock(side_effect=answers)):
                result = await check_attendance_location(21.25, 79.1, 21.1458, 79.0882, 1)
                self.assertIsNone(result["passed"])
                self.assertEqual(result["status"], "unavailable")

    async def test_invalid_gps_does_not_pass_or_call_provider(self):
        with patch("app.services.location_policy.resolve_city", new_callable=AsyncMock) as lookup:
            result = await check_attendance_location(float("nan"), 79, 21, 79, 5)
            self.assertIsNone(result["passed"])
            lookup.assert_not_awaited()


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_skips_http(self):
        redis = AsyncMock()
        redis.__aenter__.return_value = redis
        redis.get.return_value = '{"city":"Nagpur"}'
        with patch("app.services.city_lookup.get_redis", return_value=redis), patch("app.services.city_lookup.httpx.AsyncClient") as http:
            self.assertEqual((await resolve_city(21, 79))["city"], "Nagpur")
            http.assert_not_called()

    async def test_timeout_caches_failure_and_keeps_cooldown(self):
        redis = AsyncMock()
        redis.__aenter__.return_value = redis
        redis.get.return_value = None
        redis.set.return_value = True
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.side_effect = httpx.ReadTimeout("timeout")
        with patch("app.services.city_lookup.get_redis", return_value=redis), patch("app.services.city_lookup.httpx.AsyncClient", return_value=client):
            self.assertEqual(await resolve_city(21, 79), {})
            self.assertEqual(redis.set.await_args.kwargs["ex"], 60)
            redis.eval.assert_awaited_once()

    async def test_provider_success_is_cached(self):
        redis = AsyncMock()
        redis.__aenter__.return_value = redis
        redis.get.return_value = None
        redis.set.return_value = True
        client = AsyncMock()
        client.__aenter__.return_value = client
        response = Mock()
        response.json.return_value = {"address": AREA, "display_name": "Nagpur, India"}
        client.get.return_value = response
        with patch("app.services.city_lookup.get_redis", return_value=redis), patch("app.services.city_lookup.httpx.AsyncClient", return_value=client):
            self.assertEqual((await resolve_city(21, 79))["city"], "Nagpur")
            self.assertEqual(redis.set.await_args.kwargs["ex"], 2592000)
            redis.eval.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
