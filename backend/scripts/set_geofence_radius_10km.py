"""Set every existing roster record's allowed radius to 10 km.

Run without --apply first to preview the target database and row count.
The script only updates SQL Server JSON roster documents when --apply is set.
"""

import argparse
import asyncio

from sqlalchemy import text

from app.config import settings
from app.db.mssql import get_engine


async def main(apply: bool) -> None:
    engine = get_engine()
    try:
        async with engine.begin() as connection:
            count = await connection.execute(text(
                "SELECT COUNT(*) FROM dbo.attendance_roster"
            ))
            rows = int(count.scalar_one())
            print(
                f"Database target: {settings.mssql_server}/{settings.mssql_database}"
            )
            print(f"Roster records to set to 10 km: {rows}")
            if not apply:
                print("Preview only. Re-run with --apply to update these records.")
                return

            await connection.execute(text(
                "UPDATE dbo.attendance_roster "
                "SET data_json = JSON_MODIFY(data_json, '$.geofence_radius_km', 10.0)"
            ))
            print(f"Updated {rows} roster records to 10 km.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write 10 km to every existing roster record",
    )
    args = parser.parse_args()
    asyncio.run(main(args.apply))
