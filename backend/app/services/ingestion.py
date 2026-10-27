"""Unified AI attendance processing pipeline.

Performs verification inside the Redis worker, enforces a single submission
per calendar day in IST, validates the GPS photo timestamp, and logs flag reasons.
"""
import logging
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from app.db.database import (
    create_notification,
    get_db,
    get_enrollment,
    get_retryable_submission_today,
    has_submission_today,
    lookup_roster,
    normalize_phone,
    delete_system_absences_today,
)
from app.redis_queue import NOTIFICATION_STREAM, enqueue, get_redis
from app.schemas import InteraktWebhookPayload
from app.services.alert_formatting import format_issues_for_alert
from app.services.duplicate_check import compute_image_hash, is_duplicate
from app.services.face_detect import detect_face
from app.services.face_match import verify_identity
from app.services.location_policy import check_attendance_location
from app.services.liveness import check_passive_liveness
from app.services.ocr import OverlayData, extract_overlay_data
from app.services.shift_check import NON_FAILURE_STATUSES, check_shift_window
from app.services.whatsapp_reply import build_submission_reply

logger = logging.getLogger("ingestion")
INDIA_TZ = ZoneInfo("Asia/Kolkata")


def _get_today_ist() -> str:
    """Calendar date in Indian Standard Time (YYYY-MM-DD)."""
    return datetime.now(INDIA_TZ).strftime("%Y-%m-%d")


def _exif_date_mismatch(overlay: OverlayData) -> str | None:
    if overlay.timestamp is None or overlay.exif_timestamp is None:
        return None

    overlay_date = overlay.timestamp.astimezone(INDIA_TZ).date()
    exif_date = overlay.exif_timestamp.date()
    return exif_date.isoformat() if overlay_date != exif_date else None


def _duplicate_date_issue(photo_date: str | None, past_submission: dict) -> str | None:
    previous_photo_date = past_submission.get("photo_date")
    if photo_date and previous_photo_date and photo_date != previous_photo_date:
        return f"possible_date_edit_near_duplicate_{previous_photo_date}"
    return None


def _previous_attempt_history(retry_submission: dict | None) -> list[dict]:
    if retry_submission is None:
        return []

    history = list(retry_submission.get("previous_flagged_attempts") or [])
    history.append({
        "submission_id": str(retry_submission["_id"]),
        "event_id": retry_submission.get("event_id"),
        "attendance_date": retry_submission.get("attendance_date"),
        "photo_date": retry_submission.get("photo_date"),
        "flag_reason": retry_submission.get("flag_reason"),
        "issues": retry_submission.get("issues") or [],
        "received_at_utc": retry_submission.get("received_at_utc"),
    })
    return history


async def download_media(media_url: str) -> bytes:
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(media_url)
        response.raise_for_status()
        return response.content


def _notification_id(event_id: str, kind: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"attendance:{event_id}:{kind}"))


async def _queue_notification(job: dict) -> None:
    stored_job = dict(job)
    await create_notification(stored_job)

    redis = get_redis()
    try:
        await enqueue(redis, NOTIFICATION_STREAM, job)
    finally:
        await redis.close()


async def queue_submission_notifications(
    event_id: str,
    payload: InteraktWebhookPayload,
    submission: dict,
) -> None:
    roster_name = submission.get("employee_name")
    verdict = submission.get("verdict")
    issues = submission.get("issues", [])

    reply = build_submission_reply(submission)
    if reply is not None:
        await _queue_notification({
            "notification_id": _notification_id(event_id, "employee_reply"),
            "event_id": event_id,
            "kind": "employee_reply",
            "status": "pending",
            "attempt": 0,
            "country_code": payload.data.customer.country_code,
            "phone_number": payload.data.customer.phone_number,
            "message": reply,
        })

    if verdict != "verified":
        overlay = submission.get("overlay") or {}
        timestamp = overlay.get("timestamp")
        time_display = "Unknown"
        if timestamp:
            try:
                dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                time_display = dt.strftime("%d/%m/%Y, %I:%M %p")
            except ValueError:
                time_display = str(timestamp)
        await _queue_notification({
            "notification_id": _notification_id(event_id, "admin_alert"),
            "event_id": event_id,
            "kind": "admin_alert",
            "status": "pending",
            "attempt": 0,
            "employee_name": roster_name or f"Unknown ({submission.get('sender_phone')})",
            "site": submission.get("site_name") or "N/A",
            "issue_text": format_issues_for_alert(issues),
            "time_str": time_display,
        })


async def process_attendance_submission(
    payload: InteraktWebhookPayload,
    event_id: str,
) -> None:
    msg = payload.data.message
    if msg.message_content_type != "Image":
        logger.info("Ignoring non-image message from %s", payload.data.customer.channel_phone_number)
        return

    db = get_db()
    existing = await db.submissions.find_one({"event_id": event_id})
    if existing:
        existing["_id"] = str(existing["_id"])
        if existing.get("employee_id") and existing.get("attendance_date"):
            await delete_system_absences_today(
                existing["employee_id"], existing["attendance_date"]
            )
        await queue_submission_notifications(event_id, payload, existing)
        return

    sender_phone = normalize_phone(payload.data.customer.channel_phone_number or payload.data.customer.phone_number)
    caption = msg.message or ""
    media_url = msg.media_url
    issues: list[str] = []
    today_ist = _get_today_ist()
    logger.info("Processing attendance submission from %s event=%s date=%s", sender_phone, event_id, today_ist)

    roster_entry = await lookup_roster(sender_phone)
    if roster_entry is None:
        issues.append("unregistered_phone_number")
    elif roster_entry.role == "PC":
        logger.info(
            "Ignoring attendance image from project coordinator %s event=%s",
            roster_entry.employee_id,
            event_id,
        )
        return

    if roster_entry is not None and not roster_entry.is_active:
        if not media_url:
            return
        image_bytes = await download_media(media_url)
        new_hash = compute_image_hash(image_bytes)
        submission = {
            "event_id": event_id,
            "employee_id": roster_entry.employee_id,
            "employee_name": roster_entry.name,
            "person_role": roster_entry.role,
            "pc_id": roster_entry.pc_id,
            "parent_employee_id": roster_entry.parent_employee_id,
            "sender_phone": sender_phone,
            "caption": caption,
            "media_url": media_url,
            "image_hash": str(new_hash),
            "attendance_date": today_ist,
            "attendance_status": "absent",
            "verdict": "inactive_account",
            "review_status": "n/a",
            "issues": ["employee_inactive"],
            "flag_reason": "INACTIVE",
            "received_at_utc": msg.received_at_utc,
            "entry_type": "whatsapp",
        }
        await db.submissions.insert_one(submission)
        await queue_submission_notifications(event_id, payload, submission)
        return

    retry_submission = None
    previous_flagged_attempts: list[dict] = []
    if roster_entry is not None and await has_submission_today(
        roster_entry.employee_id, today_ist, include_system_absences=False
    ):
        retry_submission = await get_retryable_submission_today(
            roster_entry.employee_id, today_ist
        )
        if retry_submission is None:
            return
        logger.info(
            "Accepting replacement photo from %s for pending submission %s",
            sender_phone,
            retry_submission.get("_id"),
        )
        previous_flagged_attempts = _previous_attempt_history(retry_submission)

    if not media_url:
        logger.error("No media_url in payload — cannot process image")
        return
    image_bytes = await download_media(media_url)

    location_check_enabled = not (
        roster_entry is not None and roster_entry.role == "FS"
        and roster_entry.location_check_enabled is False
    )
    overlay = extract_overlay_data(image_bytes)
    if not location_check_enabled and overlay.timestamp is None:
        issues.append("photo_timestamp_missing")
    elif location_check_enabled and not overlay.extraction_complete:
        issues.append("overlay_extraction_incomplete")

    # Validate photo capture date matches current day
    photo_date = None
    photo_timestamp_iso = None
    if overlay.timestamp is not None:
        photo_timestamp_iso = overlay.timestamp.isoformat()
        try:
            photo_date = overlay.timestamp.astimezone(INDIA_TZ).strftime("%Y-%m-%d")
        except Exception:
            photo_date = overlay.timestamp.strftime("%Y-%m-%d")

        if photo_date != today_ist:
            issues.append(f"date_mismatch_{photo_date}")
            logger.warning(
                "Photo date mismatch for %s: photo from %s, submitted on %s",
                sender_phone, photo_date, today_ist,
            )

    if exif_date := _exif_date_mismatch(overlay):
        issues.append(f"exif_date_mismatch_{exif_date}")
        logger.warning(
            "Photo overlay/EXIF date mismatch for %s: overlay=%s EXIF=%s",
            sender_phone,
            photo_date,
            exif_date,
        )

    new_hash = compute_image_hash(image_bytes)
    if roster_entry:
        past_submissions = db.submissions.find({
            "employee_id": roster_entry.employee_id,
            "attendance_date": {"$ne": today_ist},
            "review_status": {"$ne": "superseded"},
        })
        async for past in past_submissions:
            if not past.get("image_hash"):
                continue
            dup, distance = is_duplicate(new_hash, past["image_hash"])
            if dup:
                issues.append(f"duplicate_of_submission_{past['_id']}")
                if date_issue := _duplicate_date_issue(photo_date, past):
                    issues.append(date_issue)
                break

    geofence_passed = None
    geofence_distance = None
    geofence_radius_meters = None
    location_result = {}
    location_match_status = None
    location_match_level = None
    expected_city = None
    expected_district = None
    attendance_city = None
    attendance_district = None
    if not location_check_enabled:
        location_match_status = "disabled"
        location_result = {"method": "disabled"}
    elif roster_entry and roster_entry.assigned_site and overlay.latitude is not None and overlay.longitude is not None:
        assigned_site = roster_entry.assigned_site
        location_result = await check_attendance_location(
            overlay.latitude, overlay.longitude, assigned_site.lat, assigned_site.long,
            roster_entry.geofence_radius_km,
        )
        location_match_level = "city"
        geofence_passed = location_result["passed"]
        geofence_distance = location_result["distance"]
        geofence_radius_meters = location_result["radius"]
        location_match_status = location_result["status"]
        expected_city = location_result["assigned"].get("city")
        expected_district = location_result["assigned"].get("district")
        attendance_city = location_result["actual"].get("city")
        attendance_district = location_result["actual"].get("district")
        if geofence_passed is None:
            issues.append("location_city_unavailable")
        elif not geofence_passed:
            issues.append("location_outside_range_and_city")
    elif roster_entry and not roster_entry.assigned_site:
        issues.append("assigned_site_not_configured")
    elif roster_entry and (overlay.latitude is None or overlay.longitude is None):
        issues.append("photo_gps_missing")

    face_present, face_count = detect_face(image_bytes)
    if not face_present:
        issues.append("no_face_detected")

    liveness_status, liveness_issues, liveness_metrics = check_passive_liveness(image_bytes)
    if liveness_status == "suspicious":
        issues.extend(f"liveness_{x}" for x in liveness_issues)

    identity_verdict = None
    identity_score = None
    if face_present and roster_entry:
        enrolled = await get_enrollment(roster_entry.employee_id)
        if not enrolled:
            issues.append("not_enrolled")
        else:
            identity_verdict, identity_score = verify_identity(image_bytes, enrolled)
            if identity_verdict != "verified":
                issues.append(f"identity_{identity_verdict}_{identity_score:.2f}")

    shift_status = None
    if overlay.timestamp is not None:
        shift_status, shift_reason = check_shift_window(
            overlay.timestamp,
            employee_shift_start=roster_entry.shift_start if roster_entry else None,
            employee_shift_end=roster_entry.shift_end if roster_entry else None,
            employee_grace_minutes=roster_entry.shift_grace_minutes if roster_entry else None,
            employee_role=roster_entry.role if roster_entry else None,
        )
        if shift_status not in NON_FAILURE_STATUSES:
            issues.append(f"shift_{shift_status}")

    verdict = "verified" if not issues else "flagged"

    flag_reason = None
    if verdict == "flagged":
        if any(
            i.startswith((
                "photo_timestamp_missing",
                "date_mismatch",
                "exif_date_mismatch",
                "possible_date_edit_near_duplicate",
            ))
            for i in issues
        ):
            flag_reason = "DATE"
        elif any("geofence" in i or i.startswith("location_") or i in {"assigned_site_not_configured", "photo_gps_missing"} for i in issues):
            flag_reason = "LOCATION"
        elif any("face" in i or "identity" in i for i in issues):
            flag_reason = "FACE"
        elif any("duplicate" in i for i in issues):
            flag_reason = "DUPLICATE"
        elif any("shift" in i for i in issues):
            flag_reason = "SHIFT"
        else:
            flag_reason = "REVIEW"

    if verdict == "verified":
        attendance_status = "absent_late" if shift_status in ("after_grace", "after_window") else ("late" if shift_status == "late" else "present")
    else:
        attendance_status = "pending"

    submission = {
        "event_id": event_id,
        "employee_id": roster_entry.employee_id if roster_entry else None,
        "employee_name": roster_entry.name if roster_entry else None,
        "person_role": roster_entry.role if roster_entry else None,
        "pc_id": roster_entry.pc_id if roster_entry else None,
        "parent_employee_id": roster_entry.parent_employee_id if roster_entry else None,
        "sender_phone": sender_phone,
        "caption": caption,
        "media_url": media_url,
        "image_hash": str(new_hash),
        "overlay": overlay.model_dump(mode="json"),
        "site_name": roster_entry.assigned_site.name if roster_entry and roster_entry.assigned_site else None,
        "geofence_passed": geofence_passed,
        "geofence_distance_m": geofence_distance,
        "geofence_radius_meters": geofence_radius_meters,
        "location_check_enabled": location_check_enabled,
        "location_check_method": location_result.get("method"),
        "location_match_status": location_match_status,
        "location_match_level": location_match_level,
        "expected_city": expected_city,
        "expected_district": expected_district,
        "attendance_city": attendance_city,
        "attendance_district": attendance_district,
        "face_present": face_present,
        "face_count": face_count,
        "liveness_status": liveness_status,
        "liveness_issues": liveness_issues,
        "liveness_metrics": liveness_metrics,
        "identity_verdict": identity_verdict,
        "identity_score": identity_score,
        "shift_status": shift_status,
        "attendance_date": today_ist,
        "photo_date": photo_date,
        "photo_timestamp": photo_timestamp_iso,
        "attendance_status": attendance_status,
        "flag_reason": flag_reason,
        "verdict": verdict,
        "review_status": "n/a" if verdict == "verified" else "pending",
        "issues": issues,
        "entry_type": "whatsapp",
        "received_at_utc": msg.received_at_utc,
    }
    if previous_flagged_attempts:
        submission["previous_flagged_attempts"] = previous_flagged_attempts

    try:
        await db.submissions.insert_one(submission)
    except Exception as exc:
        if "duplicate key" not in str(exc).lower():
            raise
        submission = await db.submissions.find_one({"event_id": event_id})
        if not submission:
            raise
    if retry_submission is not None:
        await db.submissions.update_one(
            {
                "_id": retry_submission["_id"],
                "verdict": "flagged",
                "review_status": "pending",
            },
            {
                "$set": {
                    "review_status": "superseded",
                    "superseded_by_event_id": event_id,
                }
            },
        )
    if roster_entry is not None:
        await delete_system_absences_today(roster_entry.employee_id, today_ist)

    if submission.get("_id") is not None:
        submission["_id"] = str(submission["_id"])

    await queue_submission_notifications(event_id, payload, submission)
    logger.info("Attendance event %s completed verdict=%s issues=%s", event_id, verdict, issues or "none")
