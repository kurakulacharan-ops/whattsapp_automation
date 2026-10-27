"""
Sends anomaly alerts to the admin — free-form text if their 24h WhatsApp
session window is open (they messaged recently), pre-approved template
fallback otherwise. See our design discussion: this guarantees every
alert is delivered immediately, in one form or the other, with no gaps.

Template "attendance_anomaly_alert" must be Meta-approved before the
fallback path will actually succeed — submitted, pending approval as of
this writing. The free-text path works today (uses the same confirmed
send_text_reply mechanism as employee replies).
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.db.database import get_admin_last_seen
from app.services.whatsapp_reply import send_text_reply

logger = logging.getLogger("admin_alert")

TEMPLATE_NAME = "attendance_anomaly_alert"
TEMPLATE_LANGUAGE = "en"


async def _session_window_open() -> bool:
    last_seen = await get_admin_last_seen()
    if last_seen is None:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last_seen
    return age < timedelta(hours=settings.admin_session_window_hours)


async def _send_template_alert(
    employee_name: str, site: str, issue_text: str, time_str: str
) -> bool:
    """
    Send via Interakt's Template Send API — used only when the free-form
    session window is closed. Payload structure confirmed against
    Interakt's documented Send WhatsApp Template API.
    """
    payload = {
        "countryCode": settings.admin_country_code,
        "phoneNumber": settings.admin_phone_number,
        "type": "Template",
        "template": {
            "name": TEMPLATE_NAME,
            "languageCode": TEMPLATE_LANGUAGE,
            "bodyValues": [employee_name, site, issue_text, time_str],
        },
    }
    headers = {
        "Authorization": f"Basic {settings.interakt_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.interakt.ai/v1/public/message/",
                json=payload, headers=headers, timeout=15.0,
            )
        response.raise_for_status()
        result = response.json()
        if not result.get("result"):
            logger.error("Interakt rejected template alert: %s", result)
            return False
        logger.info("Template alert sent (id: %s)", result.get("id"))
        return True
    except httpx.HTTPStatusError as exc:
        # Log the actual response body — Interakt's error detail (e.g.
        # "template not approved") is in here, not in the exception's str()
        logger.error(
            "Failed to send template alert: %s — response body: %s",
            exc, exc.response.text,
        )
        return False
    except Exception as exc:
        logger.error("Failed to send template alert: %s", exc)
        return False


async def send_admin_alert(
    employee_name: str, site: str, issue_text: str, time_str: str
) -> bool:
    """
    Main entry point — picks free-text or template based on whether the
    admin's session window is currently open. Called from ingestion.py
    whenever a submission is flagged.
    """
    if not settings.admin_phone_number:
        logger.warning("No admin phone number configured — alert not sent")
        return False

    window_open = await _session_window_open()

    if window_open:
        message = (
            f"⚠️ Attendance anomaly detected.\n\n"
            f"Employee: {employee_name}\n"
            f"Site: {site}\n"
            f"Issue: {issue_text}\n"
            f"Time: {time_str}\n\n"
            f"Please review in the admin dashboard."
        )
        logger.info("Admin session open — sending free-text alert")
        return await send_text_reply(
            settings.admin_country_code, settings.admin_phone_number, message
        )
    else:
        logger.info("Admin session closed — falling back to template")
        return await _send_template_alert(employee_name, site, issue_text, time_str)