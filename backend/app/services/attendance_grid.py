"""
Build date-wise attendance results from SQL Server submissions.

Markers:
    P   = Present and on time
    L   = Present but late
    A   = Absent
    AL  = Absent or checked in after the allowed shift window
    HD  = Half day
    WO  = Week off
    H   = Holiday
    F   = Flagged, awaiting review
        Admin changes override this daily marker without replacing submission history.
    M   = Manual attendance entry
    N/A = Employee inactive on that date
    —   = Today/future date with no submission yet
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NO_RESULT = "—"


def daterange(date_from: str, date_to: str) -> list[str]:
    """Return inclusive YYYY-MM-DD date strings."""
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)

    if end < start:
        raise ValueError("date_to must be on or after date_from")

    days = []
    current = start

    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)

    return days


def marker_for_submission(sub: dict | None) -> str:
    """Convert one SQL Server submission into a daily attendance marker."""
    if not sub:
        return "A"

    if sub.get("attendance_code"):
        return sub["attendance_code"]

    if sub.get("verdict") == "inactive_account":
        return "N/A"

    if sub.get("entry_type") == "manual":
        return "M"

    verdict = sub.get("verdict")
    review_status = sub.get("review_status")
    shift_status = sub.get("shift_status")
    attendance_status = sub.get("attendance_status")

    if verdict == "flagged":
        if review_status == "approved":
            return "AL" if shift_status in ("after_grace", "after_window") else ("L" if shift_status == "late" else "P")
        if review_status == "rejected":
            return "A"
        return "F"

    if attendance_status == "pending":
        return "F"
    if shift_status in ("after_grace", "after_window") or attendance_status == "absent_late":
        return "AL"
    if attendance_status == "absent":
        return "A"
    if attendance_status in ("present", "late"):
        return "L" if (shift_status == "late" or attendance_status == "late") else "P"

    if verdict == "verified":
        if shift_status == "after_window":
            return "A"
        return "AL" if shift_status in ("after_grace", "after_window") else ("L" if shift_status == "late" else "P")

    return "A"


def is_employee_included(
    is_active: bool,
    deactivated_at: str | None,
    date_from: str,
) -> bool:
    """Exclude employees deactivated before the report period began."""
    if is_active or not deactivated_at:
        return True
    return deactivated_at[:10] >= date_from


def _today_local() -> str:
    """Use India local date for attendance reporting."""
    try:
        return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def compute_employee_grid(
    is_active: bool,
    deactivated_at: str | None,
    submissions_by_date: dict,
    days: list[str],
    today: str | None = None,
) -> dict[str, str] | None:
    """Return one non-empty attendance marker for every date in the range."""
    if not days:
        return {}

    if not is_employee_included(is_active, deactivated_at, days[0]):
        return None

    if today is None:
        today = _today_local()

    grid = {}

    for day in days:
        if deactivated_at and day > deactivated_at[:10]:
            grid[day] = "N/A"
            continue

        submission = submissions_by_date.get(day)

        if submission is not None:
            grid[day] = marker_for_submission(submission)
        elif day < today:
            grid[day] = "A"
        else:
            grid[day] = NO_RESULT

    return grid
