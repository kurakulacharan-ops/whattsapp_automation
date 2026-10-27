"""
Converts internal issue codes into human-readable text for WhatsApp
alerts and dashboard display, and maps issues to short flag categories
(DATE, LOCATION, FACE, SHIFT, DUPLICATE).
"""
import re

_STATIC_LABELS = {
    "unregistered_phone_number": "Unregistered phone number — no roster match",
    "photo_timestamp_missing": "Could not read the photo date/time",
    "overlay_extraction_incomplete": "Could not read location/time from photo overlay",
    "no_face_detected": "No face detected in photo",
    "not_enrolled": "Employee not yet enrolled for face verification",
    "employee_inactive": "Submission from a deactivated employee",
    "shift_before_window": "Submitted before allowed shift window",
    "shift_after_window": "Submitted after allowed shift window",
    "shift_unparseable": "Shift time parsing failure",
    "assigned_site_not_configured": "Assigned site location not configured in roster",
    "assigned_city_not_configured": "Assigned city not configured in roster",
    "assigned_district_not_configured": "Assigned district not configured in roster",
    "location_city_unavailable": "Outside assigned range; city/town could not be verified — manual review required",
    "location_outside_range_and_city": "Outside assigned range and city/town — manual review required",
    "location_boundary_uncertain": "GPS is near a district boundary; manual review required",
    "location_lookup_unavailable": "Unable to verify city/district from GPS coordinates",
    "location_place_unavailable": "Could not read a place name from the attendance photo",
    "location_district_unavailable": "Could not determine the attendance district",
    "location_out_of_area": "Attendance photo was outside the assigned city/district",
}


def _format_one(issue: str) -> str:
    if issue in _STATIC_LABELS:
        return _STATIC_LABELS[issue]

    if match := re.match(r"date_mismatch_(.+)", issue):
        return f"Photo date mismatch (Photo taken on {match.group(1)}, not today)"

    if match := re.match(r"exif_date_mismatch_(.+)", issue):
        return f"Photo date differs from its camera metadata (metadata date: {match.group(1)})"

    if match := re.match(r"possible_date_edit_near_duplicate_(.+)", issue):
        return (
            "Near-identical photo has a different overlay date than a previous "
            f"submission (previous date: {match.group(1)}; possible date edit or photo reuse)"
        )

    if match := re.match(r"geofence_fail_(\d+)m", issue):
        return f"Location mismatch — {match.group(1)}m from assigned site"

    if match := re.match(r"duplicate_of_submission_(.+)", issue):
        return "Duplicate/reused photo detected"

    if match := re.match(r"identity_(uncertain|rejected)_([\d.]+)", issue):
        verdict = match.group(1)
        label = "needs review" if verdict == "uncertain" else "didn't match"
        return f"Face verification {label}"

    if match := re.match(r"liveness_(.+)", issue):
        return f"Anti-spoofing warning: {match.group(1)}"

    return issue


def format_issues_for_alert(issues: list[str]) -> str:
    """Joins multiple issues into one readable line for WhatsApp alerts."""
    if not issues:
        return "Unknown issue"
    return "; ".join(_format_one(i) for i in issues)


def format_issue_list(issues: list[str]) -> list[str]:
    """Returns human-readable strings for API response issues_display."""
    return [_format_one(i) for i in issues]


def flag_reason_from_issues(issues: list[str]) -> str | None:
    """
    Computes the concise badge label (DATE, LOCATION, FACE, SHIFT, DUPLICATE)
    shown in the admin console Flag column.
    """
    if not issues:
        return None

    for issue in issues:
        if issue.startswith((
            "date_mismatch",
            "exif_date_mismatch",
            "possible_date_edit_near_duplicate",
        )):
            return "DATE"

    for issue in issues:
        if (
            "geofence" in issue
            or issue.startswith("location_")
            or issue.startswith("assigned_city")
            or issue.startswith("assigned_district")
        ):
            return "LOCATION"

    for issue in issues:
        if "face" in issue or "identity" in issue or "liveness" in issue:
            return "FACE"

    for issue in issues:
        if "duplicate" in issue:
            return "DUPLICATE"

    for issue in issues:
        if "shift" in issue:
            return "SHIFT"

    return "REVIEW"
