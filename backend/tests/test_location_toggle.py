import unittest
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.db.database import RosterEntry, EmployeeRegistrationRequest, EmployeeUpdateRequest
from app.services.ingestion import process_attendance_submission
from app.services.ocr import OverlayData


class Cursor:
    def __init__(self, values):
        self.values = values
    def __aiter__(self):
        async def items():
            for value in self.values:
                yield value
        return items()


class LocationToggleTests(unittest.IsolatedAsyncioTestCase):
    async def run_pipeline(self, enabled=False, role="FS", gps=False, timestamp=True, face=True, duplicate=False, wrong_date=False):
        roster = RosterEntry(employee_id="TEST001", phone_number="919123456789", name="Test", role=role, location_check_enabled=enabled,
            assigned_site={"name":"Site", "lat":21, "long":79} if gps else None)
        capture = datetime.fromisoformat("2026-10-22T07:00:00+05:30" if wrong_date else "2026-10-23T07:00:00+05:30") if timestamp else None
        overlay = OverlayData(raw_text="", timestamp=capture, latitude=22 if gps else None, longitude=80 if gps else None, extraction_complete=gps and timestamp)
        subs = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock(), find=Mock(return_value=Cursor([{"_id":"old", "image_hash":"old"}] if duplicate else [])))
        payload = SimpleNamespace(data=SimpleNamespace(
            customer=SimpleNamespace(channel_phone_number="919123456789", phone_number="9123456789", country_code="+91"),
            message=SimpleNamespace(message_content_type="Image", message="", media_url="https://example.invalid/test.jpg", received_at_utc="2026-10-23T01:30:00Z")))
        location = AsyncMock(return_value={"passed":False,"distance":200000,"radius":8000,"status":"out_of_area","method":"range_then_city","assigned":{"city":"Nagpur"},"actual":{"city":"Other"}})
        replacements = {
            "get_db": Mock(return_value=SimpleNamespace(submissions=subs)),
            "lookup_roster": AsyncMock(return_value=roster),
            "_get_today_ist": Mock(return_value="2026-10-23"),
            "has_submission_today": AsyncMock(return_value=False),
            "download_media": AsyncMock(return_value=b"test"),
            "extract_overlay_data": Mock(return_value=overlay),
            "compute_image_hash": Mock(return_value="new"),
            "is_duplicate": Mock(return_value=(True,0)),
            "detect_face": Mock(return_value=(face,1 if face else 0)),
            "check_passive_liveness": Mock(return_value=("ok",[],{})),
            "get_enrollment": AsyncMock(return_value={"embeddings":[1]}),
            "verify_identity": Mock(return_value=("verified",0.99)),
            "delete_system_absences_today": AsyncMock(),
            "queue_submission_notifications": AsyncMock(),
            "check_attendance_location": location,
        }
        with ExitStack() as stack:
            for name, replacement in replacements.items():
                stack.enter_context(patch("app.services.ingestion."+name, replacement))
            await process_attendance_submission(payload, "test-event")
        return subs.insert_one.await_args.args[0], location

    async def test_disabled_fs_without_gps_or_site_is_verified(self):
        result, location = await self.run_pipeline()
        self.assertEqual(result["verdict"], "verified")
        self.assertEqual(result["location_match_status"], "disabled")
        self.assertFalse(result["location_check_enabled"])
        self.assertIsNone(result["geofence_passed"])
        location.assert_not_awaited()

    async def test_disabled_fs_outside_area_skips_check(self):
        result, location = await self.run_pipeline(gps=True)
        self.assertEqual(result["issues"], [])
        location.assert_not_awaited()

    async def test_enabled_fs_outside_area_is_flagged(self):
        result, location = await self.run_pipeline(enabled=True, gps=True)
        self.assertIn("location_outside_range_and_city", result["issues"])
        self.assertEqual(result["flag_reason"], "LOCATION")
        location.assert_awaited_once()

    async def test_enabled_fs_missing_gps_still_flags(self):
        result, _ = await self.run_pipeline(enabled=True)
        self.assertEqual(result["verdict"], "flagged")
        self.assertIn("overlay_extraction_incomplete", result["issues"])

    async def test_other_roles_cannot_bypass_location(self):
        for role in ("LS", "LSS"):
            result, location = await self.run_pipeline(role=role, gps=True)
            self.assertTrue(result["location_check_enabled"])
            self.assertEqual(result["verdict"], "flagged")
            location.assert_awaited_once()

    async def test_other_validation_remains_active(self):
        for options, expected in [({"timestamp":False},"photo_timestamp_missing"), ({"wrong_date":True},"date_mismatch_2026-10-22"), ({"face":False},"no_face_detected"), ({"duplicate":True},"duplicate_of_submission_old")]:
            result, location = await self.run_pipeline(**options)
            self.assertEqual(result["verdict"], "flagged")
            self.assertIn(expected, result["issues"])
            location.assert_not_awaited()

    def test_model_defaults_and_partial_update(self):
        self.assertTrue(RosterEntry(employee_id="TEST", phone_number="919123456789",name="Test").location_check_enabled)
        self.assertTrue(EmployeeRegistrationRequest(phone_number="919123456789",name="Test").location_check_enabled)
        self.assertNotIn("location_check_enabled", EmployeeUpdateRequest().model_dump(exclude_unset=True))
        self.assertEqual(EmployeeUpdateRequest(location_check_enabled=False).model_dump(exclude_unset=True), {"location_check_enabled":False})


if __name__ == "__main__":
    unittest.main()
