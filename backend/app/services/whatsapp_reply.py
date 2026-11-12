"""
Sends free-form text replies to employees via Interakt's Send Message API.

CONFIRMED working via live test against the real Interakt account:
  POST https://api.interakt.ai/v1/public/message/
  { "countryCode": "+91", "phoneNumber": "...", "type": "Text",
    "data": { "message": "..." } }
  -> {"result": true, "message": "Message queued...", "id": "..."}

Only works within the 24-hour session window (employee must have messaged
first) — which is always true here, since this fires in response to their
own selfie submission.
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("whatsapp_reply")

INTERAKT_MESSAGE_URL = "https://api.interakt.ai/v1/public/message/"


async def send_text_reply(country_code: str, phone_number: str, message: str) -> bool:
    """
    Send a free-form text reply to an employee.

    Args:
        country_code: e.g. "+91" (matches Interakt's Customer.country_code field)
        phone_number: WITHOUT country code, e.g. "9123360859"
                      (matches Interakt's Customer.phone_number field —
                      do NOT pass the combined channel_phone_number here)
        message: plain text, sent as-is

    Returns True if Interakt accepted/queued the message, False otherwise.
    Never raises — a failed reply should not crash the pipeline; log and move on.
    """
    payload = {
        "countryCode": country_code,
        "phoneNumber": phone_number,
        "type": "Text",
        "data": {"message": message},
    }
    api_key = settings.interakt_api_key.strip()

    logger.info(
        "INTERAKT KEY INSIDE send_text_reply: loaded=%s length=%d",
        bool(api_key),
        len(api_key),
    )

    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                INTERAKT_MESSAGE_URL, json=payload, headers=headers, timeout=15.0
            )
        response.raise_for_status()
        result = response.json()
        if not result.get("result"):
            logger.warning("Interakt rejected reply to %s: %s", phone_number, result)
            return False
        logger.info("Reply sent to %s (message id: %s)", phone_number, result.get("id"))
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to send reply to %s: %s — response body: %s",
            phone_number, exc, exc.response.text,
        )
        return False
    except Exception as exc:
        logger.error("Failed to send reply to %s: %s", phone_number, exc)
        return False


def build_reply_message(
    verdict: str,
    roster_name: str | None,
    issues: list[str],
    previous_flagged_attempts: list[dict[str, Any]] | None = None,
) -> str:
    """
    Human-readable reply text for the employee — plain language, not
    internal issue codes (those are for the admin alert / DB record).
    """
    if verdict == "verified":
        name = roster_name or "there"
        message = f"✅ Attendance recorded, {name}. Thanks!\n✅ उपस्थिती नोंदवली आहे, {name}. धन्यवाद!"
        if previous_flagged_attempts:
            message += "\nYour replacement photo was accepted.\nतुमचा पर्यायी फोटो स्वीकारला आहे."
        return message
    if "unregistered_phone_number" in issues or "employee_inactive" in issues:
        return (
            "⚠️ Attendance could not be recorded. Your phone is not linked to an active account.\n"
            "⚠️ उपस्थिती नोंदवता आली नाही. तुमचा फोन सक्रिय खात्याशी जोडलेला नाही."
        )
    if "not_enrolled" in issues:
        return (
            "⚠️ Your attendance photo could not be verified. Reason: Face enrollment is incomplete.\n"
            "⚠️ तुमचा उपस्थितीचा फोटो पडताळता आला नाही. कारण: चेहरा नोंदणी पूर्ण नाही."
        )
    if any(issue.startswith(("date_mismatch", "exif_date_mismatch", "possible_date_edit")) for issue in issues):
        reason = "Photo date mismatch"
    elif any("duplicate" in issue for issue in issues):
        reason = "Duplicate or reused photo"
    elif any(
        "geofence" in issue
        or issue.startswith(("location_", "assigned_city", "assigned_district"))
        or issue == "photo_gps_missing"
        for issue in issues
    ):
        reason = "Outside assigned range/city or location could not be verified"
    elif any("face" in issue or "identity" in issue for issue in issues):
        reason = "Face verification failed"
    elif "photo_timestamp_missing" in issues:
        reason = "Photo date/time is missing or unclear"
    elif "overlay_extraction_incomplete" in issues:
        reason = "Date, time, or location is missing or unclear"
    elif any("liveness" in issue for issue in issues):
        reason = "Photo verification check failed"
    else:
        reason = "Photo details need review"
    mr_reasons = {
        "Photo date mismatch": "फोटोवरील तारीख जुळत नाही",
        "Duplicate or reused photo": "डुप्लिकेट किंवा पुन्हा वापरलेला फोटो",
        "Outside assigned range/city or location could not be verified": "नेमून दिलेल्या क्षेत्राबाहेर आहात किंवा ठिकाण पडताळता आले नाही",
        "Face verification failed": "चेहरा पडताळता आला नाही",
        "Photo date/time is missing or unclear": "फोटोवरील तारीख किंवा वेळ उपलब्ध नाही किंवा स्पष्ट नाही",
        "Date, time, or location is missing or unclear": "तारीख, वेळ किंवा ठिकाण उपलब्ध नाही किंवा स्पष्ट नाही",
        "Photo verification check failed": "फोटो पडताळणी अयशस्वी झाली",
        "Photo details need review": "फोटोच्या तपशीलांची तपासणी आवश्यक आहे",
    }
    mr_reason = mr_reasons.get(reason, "फोटोच्या तपशीलांची तपासणी आवश्यक आहे")
    return (
        "⚠️ Your attendance photo could not be verified, so attendance is not confirmed. "
        f"Reason: {reason}.\n"
        f"⚠️ तुमचा उपस्थितीचा फोटो पडताळता आला नाही, त्यामुळे उपस्थिती निश्चित नाही. कारण: {mr_reason}."
    )

def build_submission_reply(submission: dict) -> str | None:
    """Build one bilingual message for each final attendance outcome."""
    status = submission.get("attendance_status")
    if submission.get("verdict") == "flagged" and submission.get("review_status") not in {"approved", "rejected"}:
        return build_reply_message("flagged", submission.get("employee_name"), submission.get("issues") or [])
    if submission.get("review_status") == "approved":
        return "✅ Attendance marked Present after review.\n✅ तपासणीनंतर उपस्थिती उपस्थित म्हणून नोंदवली आहे."
    if submission.get("review_status") == "rejected":
        return "⚠️ Attendance marked Absent after review.\n⚠️ तपासणीनंतर उपस्थिती अनुपस्थित म्हणून नोंदवली आहे."
    if status in {"absent_late", "absent"}:
        return (
            "⚠️ Your attendance is marked Absent due to late check-in. Your photo time is outside the allowed check-in period. Please contact your supervisor if you need a review.\n"
            "⚠️ उशिरा हजेरी पाठवल्यामुळे तुमची उपस्थिती अनुपस्थित नोंदवली आहे. फोटोवरील वेळ मान्य कालावधीबाहेर आहे. तपासणीसाठी पर्यवेक्षकाशी संपर्क साधा."
        )
    if status == "late":
        return "🕒 Your attendance is marked Late.\n🕒 तुमची उपस्थिती उशिरा म्हणून नोंदवली आहे."
    if status == "present" or submission.get("verdict") == "verified":
        return build_reply_message("verified", submission.get("employee_name"), [], submission.get("previous_flagged_attempts"))
    return None
