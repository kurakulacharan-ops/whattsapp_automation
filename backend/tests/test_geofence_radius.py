import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.db.database import (
    Coordinator,
    EmployeeRegistrationRequest,
    RosterEntry,
    _phone_number_is_registered,
    create_manual_attendance,
    delete_coordinator_if_unassigned,
    delete_employee_without_attendance,
    get_retryable_submission_today,
    has_submission_today,
    save_attendance_override,
)
from app.main import get_attendance
from app.services.geofence import check_geofence
from app.services.ingestion import (
    _duplicate_date_issue,
    _exif_date_mismatch,
    _previous_attempt_history,
    process_attendance_submission,
)
from app.services.ocr import OverlayData
from app.services.whatsapp_reply import build_reply_message
from app.schemas import InteraktWebhookPayload
from app.services.attendance_export_xlsx import build_export_workbook
from io import BytesIO
from openpyxl import load_workbook


class GeofenceRadiusTests(unittest.TestCase):
    def test_person_specific_radius_controls_geofence(self):
        within_distance = check_geofence(0.01, 0, 0, 0, radius_meters=1200)
        outside_distance = check_geofence(0.01, 0, 0, 0, radius_meters=1000)
        default_radius = check_geofence(0.01, 0, 0, 0)

        self.assertTrue(within_distance[0])
        self.assertAlmostEqual(within_distance[1], 1112, delta=2)
        self.assertFalse(outside_distance[0])
        self.assertTrue(default_radius[0])

    def test_existing_and_new_people_default_to_eight_kilometers(self):
        self.assertEqual(
            RosterEntry(phone_number="911234567890", employee_id="FS001", name="Supervisor")
            .geofence_radius_km,
            8,
        )
        self.assertEqual(
            EmployeeRegistrationRequest(
                phone_number="911234567890", name="Supervisor"
            ).geofence_radius_km,
            8,
        )

    def test_radius_must_be_positive(self):
        with self.assertRaises(ValidationError):
            EmployeeRegistrationRequest(
                phone_number="911234567890",
                name="Supervisor",
                geofence_radius_km=-1,
            )

    def test_coordinator_profile_has_no_attendance_or_location_settings(self):
        coordinator = Coordinator(
            pc_id="PC001",
            name="Coordinator",
            assigned_site={"name": "Old site", "lat": 1, "long": 2},
        )
        self.assertNotIn("assigned_site", coordinator.model_dump())
        self.assertNotIn("geofence_radius_km", coordinator.model_dump())
        self.assertNotIn("shift_start", coordinator.model_dump())


class SubmissionDuplicateQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_absence_is_excluded_for_late_attendance(self):
        database = _FakeDatabase()
        with patch("app.db.database.get_db", return_value=database):
            exists = await has_submission_today(
                "PC001", "2026-10-14", include_system_absences=False
            )

        self.assertFalse(exists)
        self.assertEqual(
            database.submissions.query["$nor"],
            [{"entry_type": "system", "attendance_status": "absent"}],
        )

    async def test_system_absence_is_included_for_absence_finalization(self):
        database = _FakeDatabase()
        with patch("app.db.database.get_db", return_value=database):
            await has_submission_today("PC001", "2026-10-14")

        self.assertNotIn("$nor", database.submissions.query)


class RetryableSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresolved_flagged_whatsapp_submission_can_be_retried(self):
        database = _FakeDatabase()
        database.submissions.result = {
            "entry_type": "whatsapp",
            "verdict": "flagged",
            "review_status": "pending",
        }
        with patch("app.db.database.get_db", return_value=database):
            result = await get_retryable_submission_today("EMP001", "2026-10-15")

        self.assertEqual(result, database.submissions.result)

    async def test_verified_submission_cannot_be_retried(self):
        database = _FakeDatabase()
        database.submissions.result = {
            "entry_type": "whatsapp",
            "verdict": "verified",
            "review_status": "n/a",
        }
        with patch("app.db.database.get_db", return_value=database):
            result = await get_retryable_submission_today("EMP001", "2026-10-15")

        self.assertIsNone(result)

    async def test_manual_attendance_override_prevents_retry(self):
        database = _FakeDatabase()
        database.attendance_overrides.result = {"_id": "override"}
        with patch("app.db.database.get_db", return_value=database):
            result = await get_retryable_submission_today("EMP001", "2026-10-15")

        self.assertIsNone(result)


class PhotoDateValidationTests(unittest.TestCase):
    def test_exif_date_is_compared_with_overlay_date_in_india_time(self):
        overlay = OverlayData(
            raw_text="",
            timestamp=datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc),
            exif_timestamp=datetime(2026, 10, 15, 1, 30),
        )
        self.assertIsNone(_exif_date_mismatch(overlay))

        overlay.exif_timestamp = datetime(2026, 10, 14, 1, 30)
        self.assertEqual(_exif_date_mismatch(overlay), "2026-10-14")

    def test_near_duplicate_with_different_overlay_date_is_flagged_as_possible_edit(self):
        issue = _duplicate_date_issue(
            "2026-10-15",
            {"photo_date": "2026-10-14"},
        )
        self.assertEqual(issue, "possible_date_edit_near_duplicate_2026-10-14")
        self.assertIsNone(
            _duplicate_date_issue("2026-10-15", {"photo_date": "2026-10-15"})
        )

    def test_flagged_reply_asks_employee_to_send_a_replacement_photo(self):
        reply = build_reply_message(
            "flagged", "Employee", ["date_mismatch_2026-10-14"]
        )
        self.assertIn("attendance is not confirmed", reply)
        self.assertEqual(
            reply,
            "⚠️ Your attendance photo could not be verified, so attendance is not confirmed. "
            "Reason: Photo date mismatch.",
        )

    def test_success_reply_mentions_reason_when_replacement_is_accepted(self):
        reply = build_reply_message(
            "verified",
            "Employee",
            [],
            [{"issues": ["date_mismatch_2026-10-14"]}],
        )
        self.assertEqual(
            reply,
            "✅ Attendance recorded, Employee. Thanks! Your replacement photo was accepted.",
        )

    def test_replacement_history_preserves_earlier_attempts_and_current_flag(self):
        submission = {
            "_id": "current-flag-id",
            "event_id": "current-event",
            "attendance_date": "2026-10-15",
            "photo_date": "2026-10-14",
            "flag_reason": "DATE",
            "issues": ["date_mismatch_2026-10-14"],
            "previous_flagged_attempts": [{"submission_id": "older-flag-id"}],
        }
        history = _previous_attempt_history(submission)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["submission_id"], "older-flag-id")
        self.assertEqual(history[1]["submission_id"], "current-flag-id")
        self.assertEqual(history[1]["flag_reason"], "DATE")

    def test_unregistered_employee_reply_does_not_request_another_photo(self):
        reply = build_reply_message("flagged", None, ["unregistered_phone_number"])
        self.assertIn("not linked to an active account", reply)
        self.assertNotIn("resend", reply)


class PhoneUniquenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_conflicts_are_checked_across_people_and_roles(self):
        database = _FakeDatabase()
        database.roster.result = {"employee_id": "EMP003"}
        with patch("app.db.database.get_db", return_value=database):
            roster_conflict = await _phone_number_is_registered(
                "1234567890", exclude_pc_id="PC001"
            )

        self.assertTrue(roster_conflict)
        self.assertIn("911234567890", database.roster.query["phone_number"]["$in"])

        database = _FakeDatabase()
        database.coordinators.result = {"pc_id": "PC002"}
        with patch("app.db.database.get_db", return_value=database):
            coordinator_conflict = await _phone_number_is_registered(
                "1234567890", exclude_employee_id="EMP003", exclude_pc_id="PC001"
            )

        self.assertTrue(coordinator_conflict)
        self.assertEqual(database.roster.query["employee_id"], {"$ne": "EMP003"})
        self.assertEqual(database.coordinators.query["pc_id"], {"$ne": "PC001"})


class AttendanceListTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_coordinator_role_returns_no_attendance_people(self):
        from app.db.database import list_attendance_people

        with patch("app.db.database.list_employees", new=AsyncMock()) as list_employees:
            people, total = await list_attendance_people(role="PC")

        self.assertEqual(people, [])
        self.assertEqual(total, 0)
        list_employees.assert_not_awaited()

    async def test_project_coordinator_image_is_not_replied_to_or_processed(self):
        from types import SimpleNamespace

        payload = InteraktWebhookPayload.model_validate({
            "version": "1",
            "timestamp": "2026-10-15T08:00:00Z",
            "type": "message_received",
            "data": {
                "customer": {
                    "id": "customer-1",
                    "channel_phone_number": "919123456789",
                    "phone_number": "9123456789",
                    "country_code": "+91",
                    "traits": {},
                },
                "message": {
                    "id": "message-1",
                    "chat_message_type": "Incoming",
                    "message_status": "Received",
                    "received_at_utc": "2026-10-15T08:00:00Z",
                    "message_content_type": "Image",
                    "media_url": "https://example.invalid/photo.jpg",
                },
                "channel_type": "WhatsApp",
                "organization_id": "org-1",
                "whatsapp_api_number": "919000000000",
            },
        })
        database = SimpleNamespace(
            submissions=SimpleNamespace(find_one=AsyncMock(return_value=None))
        )
        coordinator = RosterEntry(
            employee_id="PC001",
            phone_number="919123456789",
            name="Coordinator",
            role="PC",
            pc_id="PC001",
        )
        with patch("app.services.ingestion.get_db", return_value=database), \
             patch("app.services.ingestion.lookup_roster", new=AsyncMock(return_value=coordinator)), \
             patch("app.services.ingestion._queue_notification", new=AsyncMock()) as queue_notification, \
             patch("app.services.ingestion.download_media", new=AsyncMock()) as download_media:
            await process_attendance_submission(payload, "event-1")

        download_media.assert_not_awaited()
        queue_notification.assert_not_awaited()

    async def test_manual_entry_and_override_reject_project_coordinators(self):
        coordinator = RosterEntry(
            employee_id="PC001",
            phone_number="919123456789",
            name="Coordinator",
            role="PC",
            pc_id="PC001",
        )
        with patch(
            "app.db.database.get_roster_by_employee_id",
            new=AsyncMock(return_value=coordinator),
        ):
            with self.assertRaisesRegex(ValueError, "not attendance participants"):
                await create_manual_attendance("PC001", "2026-10-15", "test", "admin")
            with self.assertRaisesRegex(ValueError, "not attendance participants"):
                await save_attendance_override(
                    "PC001", "2026-10-15", "P", "test", "admin"
                )

    async def test_superseded_attempts_do_not_block_participant_deletion(self):
        from types import SimpleNamespace

        database = SimpleNamespace(
            roster=SimpleNamespace(
                find_one=AsyncMock(return_value={"employee_id": "EMP003"}),
                count_documents=AsyncMock(return_value=0),
                delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
            ),
            submissions=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
            attendance_overrides=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
            face_embeddings=SimpleNamespace(delete_one=AsyncMock()),
        )
        with patch("app.db.database.get_db", return_value=database):
            linked = await delete_employee_without_attendance("EMP003")

        self.assertEqual(linked, (0, 0, 0))
        self.assertEqual(
            database.submissions.count_documents.await_args.args[0],
            {"employee_id": "EMP003", "review_status": {"$ne": "superseded"}},
        )
        database.roster.delete_one.assert_awaited_once()

    async def test_coordinator_historical_absence_does_not_block_delete(self):
        from types import SimpleNamespace

        database = SimpleNamespace(
            coordinators=SimpleNamespace(
                find_one=AsyncMock(return_value={"pc_id": "PC001"}),
                delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
            ),
            roster=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
        )
        with patch("app.db.database.get_db", return_value=database):
            linked = await delete_coordinator_if_unassigned("PC001")

        self.assertEqual(linked, 0)
        database.coordinators.delete_one.assert_awaited_once_with({"pc_id": "PC001"})

    def test_export_keeps_coordinator_details_separate_from_staff_attendance(self):
        workbook_bytes = build_export_workbook(
            coordinators=[{"pc_id": "PC001", "name": "Coordinator"}],
            employees=[{
                "employee_id": "EMP001",
                "name": "Field Supervisor",
                "role": "FS",
                "pc_id": "PC001",
                "is_active": True,
            }],
            grids={
                "EMP001": {"2026-10-15": "P"},
                # Even if legacy data has a coordinator grid, they are not
                # an attendance participant or staff-role worksheet row.
                "PC001": {"2026-10-15": "P"},
            },
            days=["2026-10-15"],
        )
        workbook = load_workbook(BytesIO(workbook_bytes), read_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Summary", "Project Coordinators", "Field Supervisors", "Local supervisors", "Local supervisor scanning"],
        )
        self.assertEqual(workbook["Field Supervisors"].max_row, 2)
        self.assertEqual(workbook["Summary"]["B4"].value, 1)
        coordinator_sheet = workbook["Project Coordinators"]
        self.assertEqual(coordinator_sheet["B2"].value, "PC001")
        self.assertEqual(coordinator_sheet["F2"].value, 1)
        self.assertEqual(coordinator_sheet.max_column, 7)
        self.assertNotIn("2026-10-15", [cell.value for cell in coordinator_sheet[1]])

    async def test_system_absence_is_not_displayed_as_a_flagged_checkin(self):
        system_absence = {
            "employee_id": "PC001",
            "entry_type": "system",
            "attendance_status": "absent",
            "verdict": "verified",
            "review_status": "n/a",
            "issues": [],
        }
        manual_entry = {
            "employee_id": "PC002",
            "entry_type": "manual",
            "attendance_status": "present",
            "verdict": "verified",
            "review_status": "n/a",
            "issues": [],
        }
        with patch(
            "app.main.list_attendance",
            new=AsyncMock(return_value=([system_absence, manual_entry], 2)),
        ), patch("app.main.ZoneInfo", return_value=timezone.utc):
            response = await get_attendance(admin=None)

        self.assertEqual(response["records"][0]["attendance_code"], "A")
        self.assertEqual(
            response["records"][0]["review_display"],
            "System absent (no image received)",
        )
        self.assertEqual(response["records"][1]["attendance_code"], "M")

    async def test_geofence_display_includes_the_person_specific_kilometer_limit(self):
        submission = {
            "employee_id": "FS001",
            "entry_type": "whatsapp",
            "attendance_status": "pending",
            "verdict": "flagged",
            "review_status": "pending",
            "issues": ["geofence_fail_1116m"],
            "geofence_passed": False,
            "geofence_distance_m": 1116,
            "geofence_radius_meters": 1000,
        }
        with patch(
            "app.main.list_attendance",
            new=AsyncMock(return_value=([submission], 1)),
        ), patch("app.main.ZoneInfo", return_value=timezone.utc):
            response = await get_attendance(admin=None)

        self.assertEqual(
            response["records"][0]["geofence_display"],
            "Outside range (1.12 km; limit 1 km)",
        )


class _FakeDatabase:
    def __init__(self):
        self.submissions = _FakeCollection()
        self.attendance_overrides = _FakeCollection()
        self.roster = _FakeCollection()
        self.coordinators = _FakeCollection()


class _FakeCollection:
    def __init__(self, result=None):
        self.query = None
        self.result = result

    async def find_one(self, query, projection=None, sort=None):
        self.query = query
        return self.result


if __name__ == "__main__":
    unittest.main()
