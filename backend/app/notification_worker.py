"""Durable notification worker for WhatsApp/admin notifications."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db.database import (
    claim_notification,
    get_db,
    mark_notification_skipped,
    ensure_indexes,
    mark_notification_retry,
    mark_notification_sent,
)
from app.redis_queue import NOTIFICATION_STREAM, DLQ_STREAM, ensure_stream_group, get_redis, enqueue, decode_message
from app.services.admin_alert import send_admin_alert
from app.services.whatsapp_reply import send_text_reply, build_submission_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification_worker")
GROUP = "notification-workers"
CONSUMER = settings.notification_consumer_name


async def handle_entry(redis, stream_id: str, fields: dict[str, str]) -> None:
    job = await decode_message(fields)
    notification_id = job["notification_id"]
    try:
        if not await claim_notification(notification_id):
            return
        if job["kind"] == "employee_reply":
            # Recheck persisted attendance, including jobs queued before this policy.
            submission = await get_db().submissions.find_one({"event_id": job.get("event_id")}) if job.get("event_id") else None
            reply = build_submission_reply(submission or {})
            if reply is None:
                await mark_notification_skipped(notification_id)
                return
            ok = await send_text_reply(job["country_code"], job["phone_number"], reply)
        elif job["kind"] == "admin_alert":
            ok = await send_admin_alert(job["employee_name"], job["site"], job["issue_text"], job["time_str"])
        else:
            raise ValueError(f"Unknown notification kind: {job['kind']}")
        if not ok:
            raise RuntimeError("Notification provider rejected the message")
        await mark_notification_sent(notification_id)
    except Exception as exc:
        attempt = int(job.get("attempt", 0)) + 1
        job["attempt"] = attempt
        job["last_error"] = str(exc)[:2000]
        job["last_failed_at"] = datetime.now(timezone.utc).isoformat()
        await mark_notification_retry(notification_id, str(exc))
        if attempt > settings.notification_max_retries:
            await enqueue(redis, DLQ_STREAM, job)
            logger.error("Notification moved to DLQ: %s", notification_id, exc_info=True)
        else:
            await asyncio.sleep(min(settings.notification_retry_delay_seconds * attempt, 60))
            await enqueue(redis, NOTIFICATION_STREAM, job)
            logger.warning("Notification retry %s/%s: %s", attempt, settings.notification_max_retries, notification_id)
    finally:
        await redis.xack(NOTIFICATION_STREAM, GROUP, stream_id)


async def reclaim_pending(redis) -> None:
    try:
        result = await redis.xautoclaim(
            NOTIFICATION_STREAM,
            GROUP,
            CONSUMER,
            min_idle_time=60_000,
            start_id="0-0",
            count=settings.worker_batch_size,
        )
        _, entries, _ = result
        for stream_id, fields in entries:
            await handle_entry(redis, stream_id, fields)
    except Exception:
        logger.exception("Notification pending-message recovery failed")


async def run() -> None:
    if settings.database_backend == "mssql":
        await ensure_indexes()
    redis = get_redis()
    await ensure_stream_group(redis, NOTIFICATION_STREAM, GROUP)
    logger.info("Notification worker started as %s", CONSUMER)
    counter = 0
    while True:
        counter += 1
        if counter % 10 == 0:
            await reclaim_pending(redis)
        messages = await redis.xreadgroup(
            groupname=GROUP,
            consumername=CONSUMER,
            streams={NOTIFICATION_STREAM: ">"},
            count=settings.worker_batch_size,
            block=settings.worker_block_ms,
        )
        for _, entries in messages or []:
            for stream_id, fields in entries:
                await handle_entry(redis, stream_id, fields)


if __name__ == "__main__":
    asyncio.run(run())
