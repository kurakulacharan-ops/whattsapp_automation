import unittest
from datetime import datetime

from app.services.shift_check import NON_FAILURE_STATUSES, check_shift_window, role_shift_defaults


class ShiftCheckTests(unittest.TestCase):
    def test_role_default_values(self):
        self.assertEqual(role_shift_defaults("LSS"), {"shift_start": "07:00", "shift_end": "15:00", "shift_grace_minutes": 60})
        for role in ("LS", "FS"):
            self.assertEqual(role_shift_defaults(role), {"shift_start": "09:00", "shift_end": "19:00", "shift_grace_minutes": 240})

    def test_lss_grace_boundary(self):
        for clock, expected in [("07:00", "on_time"), ("07:01", "late"), ("08:00", "late"), ("08:01", "after_grace"), ("15:01", "after_grace")]:
            status, _ = check_shift_window(datetime.fromisoformat(f"2026-10-23T{clock}:00+05:30"), employee_role="LSS")
            self.assertEqual(status, expected)

    def test_ls_fs_grace_boundary(self):
        for role in ("LS", "FS"):
            for clock, expected in [("09:00", "on_time"), ("09:01", "late"), ("13:00", "late"), ("13:01", "after_grace"), ("19:01", "after_grace")]:
                status, _ = check_shift_window(datetime.fromisoformat(f"2026-10-23T{clock}:00+05:30"), employee_role=role)
                self.assertEqual(status, expected)

    def test_ist_conversion_and_explicit_override(self):
        status, _ = check_shift_window(datetime.fromisoformat("2026-10-23T02:30:00+00:00"), employee_role="LSS")
        self.assertEqual(status, "late")
        status, _ = check_shift_window(datetime.fromisoformat("2026-10-23T09:01:00+05:30"), employee_shift_start="09:00", employee_shift_end="17:00", employee_grace_minutes=0, employee_role="LSS")
        self.assertEqual(status, "after_grace")

    def test_after_grace_is_classified_without_flagging_for_shift_alone(self):
        status, reason = check_shift_window(
            datetime.fromisoformat("2026-10-16T10:19:00+05:30"),
            employee_shift_start="09:00",
            employee_shift_end="18:00",
            employee_grace_minutes=60,
        )

        self.assertEqual(status, "after_grace")
        self.assertIn("AL", reason)
        self.assertIn(status, NON_FAILURE_STATUSES)


if __name__ == "__main__":
    unittest.main()
