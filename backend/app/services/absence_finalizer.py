"""Finalize employees with no attendance at shift end (India local time).
Run this from one backend scheduler only to avoid duplicate inserts across replicas.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.db.database import (
    delete_system_absences_today,
    get_db,
    has_submission_today,
    list_attendance_people,
)
from app.config import settings

IST = ZoneInfo('Asia/Kolkata')

async def finalize_absences():
    now = datetime.now(IST)
    today = now.date().isoformat()
    db = get_db()
    people, _ = await list_attendance_people(is_active=True, page_size=100_000)
    for person in people:
        end = person.shift_end or settings.shift_window_end
        try:
            hour, minute = map(int, end.split(':'))
        except (ValueError, AttributeError):
            continue
        if now.hour * 60 + now.minute < hour * 60 + minute:
            continue
        if await has_submission_today(person.employee_id, today):
            continue
        await db.submissions.insert_one({
            'employee_id': person.employee_id,
            'employee_name': person.name,
            'person_role': person.role,
            'pc_id': person.pc_id,
            'parent_employee_id': person.parent_employee_id,
            'attendance_date': today, 'attendance_status': 'absent',
            'shift_status': None, 'verdict': 'verified', 'review_status': 'n/a',
            'entry_type': 'system', 'issues': [], 'geofence_passed': None,
            'geofence_distance_m': None, 'photo_timestamp': None,
            'received_at_utc': datetime.now(timezone.utc).isoformat(),
            'reason': 'No check-in received by shift end',
        })
        if await has_submission_today(
            person.employee_id, today, include_system_absences=False
        ):
            await delete_system_absences_today(person.employee_id, today)
