"""Unified AI attendance worker using Redis Streams consumer groups."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db.database import (
    claim_webhook_event,
    complete_webhook_event,
    ensure_indexes,
    fail_webhook_event,
)
from app.redis_queue import ATTENDANCE_STREAM, DLQ_STREAM, ensure_stream_group, get_redis, enqueue, decode_message
from app.schemas import InteraktWebhookPayload
from app.services.ingestion import process_attendance_submission

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attendance_worker")
GROUP = "attendance-workers"
CONSUMER = settings.worker_consumer_name


async def retry_or_dlq(redis, job: dict, error: Exception) -> None:
    attempt = int(job.get("attempt", 0)) + 1
    job["attempt"] = attempt
    job["last_error"] = str(error)[:2000]
    job["last_failed_at"] = datetime.now(timezone.utc).isoformat()
    if attempt > settings.worker_max_retries:
        await enqueue(redis, DLQ_STREAM, job)
        await fail_webhook_event(job["event_id"], str(error), dead_letter=True)
        logger.error("Job moved to DLQ: %s", job["event_id"], exc_info=True)
    else:
        await fail_webhook_event(job["event_id"], str(error), dead_letter=False)
        await asyncio.sleep(min(settings.worker_retry_delay_seconds * attempt, 60))
        await enqueue(redis, ATTENDANCE_STREAM, job)
        logger.warning("Attendance retry %s/%s: %s", attempt, settings.worker_max_retries, job["event_id"])


async def handle_entry(redis, stream_id: str, fields: dict[str, str]) -> None:
    job = await decode_message(fields)
    event_id = job["event_id"]
    try:
        if not await claim_webhook_event(event_id):
            logger.info("Skipping already claimed/completed event %s", event_id)
            return
        payload = InteraktWebhookPayload.model_validate(job["payload"])
        await process_attendance_submission(payload, event_id=event_id)
        await complete_webhook_event(event_id)
        logger.info("Completed attendance event %s", event_id)
    except Exception as exc:
        await retry_or_dlq(redis, job, exc)
    finally:
        await redis.xack(ATTENDANCE_STREAM, GROUP, stream_id)


async def reclaim_pending(redis) -> None:
    """Recover jobs abandoned by a dead worker."""
    try:
        result = await redis.xautoclaim(
            ATTENDANCE_STREAM,
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
        logger.exception("Pending-message recovery failed")


async def run() -> None:
    if settings.database_backend == "mssql":
        await ensure_indexes()
    redis = get_redis()
    await ensure_stream_group(redis, ATTENDANCE_STREAM, GROUP)
    logger.info("Attendance worker started as %s", CONSUMER)
    counter = 0
    while True:
        counter += 1
        if counter % 10 == 0:
            await reclaim_pending(redis)
        messages = await redis.xreadgroup(
            groupname=GROUP,
            consumername=CONSUMER,
            streams={ATTENDANCE_STREAM: ">"},
            count=settings.worker_batch_size,
            block=settings.worker_block_ms,
        )
        for _, entries in messages or []:
            for stream_id, fields in entries:
                await handle_entry(redis, stream_id, fields)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nAttendance worker stopped by user.")