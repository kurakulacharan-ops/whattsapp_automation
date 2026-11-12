"""Helpers for applying date-specific non-working calendar events."""

from datetime import date


EVENT_CODES = {
    "holiday": "H",
    "weekoff": "WO",
    "other": "H",
}


def calendar_codes_for_days(days: list[str], calendar_data: dict) -> dict[str, str]:
    """Apply Sunday defaults plus explicit date events and working-day exceptions."""
    events_by_date = {
        str(event.get("event_date")): event
        for event in calendar_data.get("events", [])
        if event.get("event_date")
    }
    result: dict[str, str] = {}
    for day in days:
        event = events_by_date.get(day)
        if event is not None:
            code = EVENT_CODES.get(event.get("kind"))
            if code:
                result[day] = code
            # Any explicit date entry overrides the recurring Sunday rule.
            continue
        try:
            date_value = date.fromisoformat(day)
        except ValueError:
            continue
        if date_value.weekday() == 6:
            result[day] = "WO"
    return result
