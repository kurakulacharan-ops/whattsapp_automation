"""Run one instance: python -m app.absence_worker"""
import asyncio
import logging
from app.services.absence_finalizer import finalize_absences
from app.config import settings
from app.db.database import ensure_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('absence_worker')

async def run():
    if settings.database_backend == "mssql":
        await ensure_indexes()
    while True:
        try:
            await finalize_absences()
        except Exception:
            logger.exception('Attendance absence finalization failed')
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(run())