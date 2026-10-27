"""Preview or migrate assigned coordinates to local district IDs; preserve originals."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.database import get_db
from app.services.location_lookup import resolve_location, DATASET_ID


async def main(apply=False):
    db = get_db()
    counts = {"updated": 0, "would_update": 0, "skipped": 0}
    try:
        async for roster in db.roster.find({}):
            site = roster.get("assigned_site")
            if not site or site.get("lat") is None or site.get("long") is None:
                counts["skipped"] += 1
                continue
            area = await resolve_location(site["lat"], site["long"])
            if area["status"] != "resolved":
                print(json.dumps({"employee_id": roster["employee_id"], "status": area["status"]}))
                counts["skipped"] += 1
                continue
            updated = {**site, "district": area["district"], "district_id": area["district_id"], "dataset_id": DATASET_ID, "match_level": "district"}
            if updated == site:
                counts["skipped"] += 1
                continue
            print(json.dumps({"employee_id": roster["employee_id"], "district": area["district"], "mode": "apply" if apply else "preview"}))
            if apply:
                changes = {"assigned_site": updated}
                if "assigned_site_before_offline_migration" not in roster:
                    changes["assigned_site_before_offline_migration"] = site
                await db.roster.update_one({"employee_id": roster["employee_id"]}, {"$set": changes})
                counts["updated"] += 1
            else:
                counts["would_update"] += 1
        print(json.dumps(counts))
    finally:
        from app.config import settings
        if settings.database_backend == "mssql":
            from app.db.mssql import close
            await close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
