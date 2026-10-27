"""Durable Redis Streams queue helpers."""
import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.config import settings

logger = logging.getLogger("redis_queue")

ATTENDANCE_STREAM = "attendance:jobs"
NOTIFICATION_STREAM = "attendance:notifications"
DLQ_STREAM = "attendance:dead-letter"


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def ensure_stream_group(redis: Redis, stream: str, group: str) -> None:
    try:
        await redis.xgroup_create(stream, group, id="0-0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue(redis: Redis, stream: str, job: dict[str, Any]) -> str:
    return await redis.xadd(
        stream,
        {"payload": json.dumps(job, separators=(",", ":"))},
        maxlen=settings.redis_stream_maxlen,
        approximate=True,
    )


async def decode_message(fields: dict[str, str]) -> dict[str, Any]:
    return json.loads(fields["payload"])
