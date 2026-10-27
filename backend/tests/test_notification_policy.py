import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.services.whatsapp_reply import build_submission_reply
from app.services.ingestion import queue_submission_notifications
from app import notification_worker as worker


class NotificationPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_routine_results_do_not_queue_employee_replies(self):
        payload = SimpleNamespace(data=SimpleNamespace(customer=SimpleNamespace(country_code="+91", phone_number="test")))
        for status, verdict in [("present", "verified"), ("late", "verified"), ("absent", "inactive_account")]:
            with self.subTest(status=status), patch("app.services.ingestion._queue_notification", new_callable=AsyncMock) as queue:
                await queue_submission_notifications("event", payload, {"verdict":verdict, "attendance_status":status})
                self.assertFalse(any(c.args[0]["kind"] == "employee_reply" for c in queue.await_args_list))

    async def test_flag_and_absent_late_queue_correct_reply(self):
        payload = SimpleNamespace(data=SimpleNamespace(customer=SimpleNamespace(country_code="+91", phone_number="test")))
        cases = [
            ({"verdict":"flagged", "issues":["face_mismatch"]}, "Face verification failed"),
            ({"verdict":"flagged", "issues":["possible_date_edit_near_duplicate_old"]}, "Photo date mismatch"),
            ({"verdict":"flagged", "issues":["duplicate_of_submission_old"]}, "Duplicate or reused photo"),
            ({"verdict":"flagged", "issues":["location_outside_range_and_city"]}, "Outside assigned range/city"),
            ({"verdict":"verified", "attendance_status":"absent_late"}, "Absent due to late"),
        ]
        for submission, expected in cases:
            with self.subTest(expected=expected), patch("app.services.ingestion._queue_notification", new_callable=AsyncMock) as queue:
                await queue_submission_notifications("event", payload, submission)
                replies = [c.args[0] for c in queue.await_args_list if c.args[0]["kind"] == "employee_reply"]
                self.assertEqual(len(replies), 1)
                self.assertIn(expected, replies[0]["message"])
                self.assertNotIn("Attendance recorded", replies[0]["message"])

    def test_successful_replacement_silent_and_flag_takes_priority(self):
        self.assertIsNone(build_submission_reply({"verdict":"verified", "attendance_status":"present", "previous_flagged_attempts":[{}]}))
        self.assertIn("Face verification failed", build_submission_reply({"verdict":"flagged", "attendance_status":"absent_late", "issues":["face_mismatch"]}))

    async def run_worker(self, submission):
        redis = SimpleNamespace(xack=AsyncMock())
        job = {"notification_id":"test", "event_id":"event", "kind":"employee_reply", "country_code":"+91", "phone_number":"test", "message":"Old success confirmation"}
        db = SimpleNamespace(submissions=SimpleNamespace(find_one=AsyncMock(return_value=submission)))
        with patch.object(worker, "decode_message", AsyncMock(return_value=job)), patch.object(worker, "claim_notification", AsyncMock(return_value=True)), patch.object(worker, "get_db", Mock(return_value=db)), patch.object(worker, "mark_notification_skipped", AsyncMock()) as skipped, patch.object(worker, "mark_notification_sent", AsyncMock()) as sent, patch.object(worker, "send_text_reply", AsyncMock(return_value=True)) as send:
            await worker.handle_entry(redis, "stream", {})
        redis.xack.assert_awaited_once()
        return skipped, sent, send

    async def test_pending_routine_and_obsolete_jobs_are_skipped(self):
        for submission in [None, {"verdict":"verified", "attendance_status":"present"}, {"verdict":"verified", "attendance_status":"late"}, {"verdict":"inactive_account", "attendance_status":"absent"}]:
            skipped, sent, send = await self.run_worker(submission)
            skipped.assert_awaited_once()
            sent.assert_not_awaited()
            send.assert_not_awaited()

    async def test_pending_absent_late_reply_is_rebuilt(self):
        skipped, sent, send = await self.run_worker({"verdict":"verified", "attendance_status":"absent_late"})
        skipped.assert_not_awaited()
        sent.assert_awaited_once()
        self.assertIn("Absent due to late", send.await_args.args[2])

    async def test_pending_flag_still_sends(self):
        skipped, sent, send = await self.run_worker({"verdict":"flagged", "issues":["face_mismatch"]})
        skipped.assert_not_awaited()
        sent.assert_awaited_once()
        self.assertIn("Face verification failed", send.await_args.args[2])

if __name__ == "__main__":
    unittest.main()
