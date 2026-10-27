"""
Checks whether the OCR'd selfie timestamp falls within the allowed
check-in window. Per-employee shift_start/shift_end/shift_grace_minutes
(set via PATCH /employees/{id}) override the role defaults
when present — most employees use the default, but a site with a
different shift pattern can be set individually.

Returns a shift status:
  "on_time"        -> at or before shift start
  "late"           -> after shift start but within grace_minutes —
                       NOT a failure, doesn't get flagged for admin review,
                       just shows as "L" instead of "P" in the export
  "after_grace"    -> after the grace period — attendance is classified as AL,
                       but shift timing alone does not flag the submission
  "unparseable"    -> configured shift time couldn't be parsed
"""
import logging
from datetime import datetime, time


logger = logging.getLogger("shift_check")

# Statuses that should NOT be added to a submission's issues list —
# the employee did submit, it's just later than the grace window.
# Shift timing is attendance classification, not fraud detection.
# Therefore no shift status by itself should make a submission FLAGGED.
NON_FAILURE_STATUSES = {
    "on_time",
    "late",
    "after_grace",
    "before_window",
    "after_window",
    "unparseable",
}


def _parse_hhmm(value: str) -> time | None:
    """Returns None (not a raised exception) if value isn't valid "HH:MM" —
    a malformed stored value must not crash the whole background pipeline
    (caught live: a roster record had a bad shift_start value)."""
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        logger.warning("Malformed shift time value, expected HH:MM: %r", value)
        return None


def role_shift_defaults(role: str | None) -> dict:
    if role == "LSS":
        return {"shift_start": "07:00", "shift_end": "15:00", "shift_grace_minutes": 60}
    return {"shift_start": "09:00", "shift_end": "19:00", "shift_grace_minutes": 240}


def check_shift_window(
    submitted_at: datetime,
    employee_shift_start: str | None = None,
    employee_shift_end: str | None = None,
    employee_grace_minutes: int | None = None,
    employee_role: str | None = None,
) -> tuple[str, str]:
    """
    Returns (status, reason). Caller decides whether the status should add
    an issue (see NON_FAILURE_STATUSES).
    """
    defaults = role_shift_defaults(employee_role)
    start_str = employee_shift_start or defaults["shift_start"]
    end_str = employee_shift_end or defaults["shift_end"]
    grace = (
        employee_grace_minutes
        if employee_grace_minutes is not None
        else defaults["shift_grace_minutes"]
    )

    shift_start = _parse_hhmm(start_str)
    shift_end = _parse_hhmm(end_str)

    if shift_start is None or shift_end is None:
        return "unparseable", f"Could not parse configured shift window (start={start_str!r}, end={end_str!r})"

    # Compare employee shift clock time in India, never the server UTC clock.
    from zoneinfo import ZoneInfo
    if submitted_at.tzinfo is not None:
        submitted_at = submitted_at.astimezone(ZoneInfo("Asia/Kolkata"))
    submitted_time = submitted_at.time()
    submitted_minutes = submitted_time.hour * 60 + submitted_time.minute
    start_minutes = shift_start.hour * 60 + shift_start.minute
    end_minutes = shift_end.hour * 60 + shift_end.minute

    # At/before start: P; after start through grace: L; beyond grace: AL.
    # A check-in after shift end is also AL, not present.
    if submitted_minutes <= start_minutes:
        return "on_time", "Check-in at or before shift start"
    if submitted_minutes <= start_minutes + max(0, grace) and submitted_minutes <= end_minutes:
        return "late", "Check-in within grace period"
    return "after_grace", "Check-in after grace period (AL)"
