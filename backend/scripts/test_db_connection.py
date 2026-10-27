"""Read-only SQL Server connectivity check; run from backend/."""
import asyncio
import sys
sys.path.insert(0, ".")
from app.db.database import get_db
from app.db.mssql import get_engine

async def main():
    try:
        result = await get_db().command("ping")
        if result.get("ok") != 1:
            raise RuntimeError("SQL Server ping failed")
        print("SQL Server connection verified (SELECT 1); no records changed.")
    finally:
        await get_engine().dispose()

if __name__ == "__main__":
    asyncio.run(main())
