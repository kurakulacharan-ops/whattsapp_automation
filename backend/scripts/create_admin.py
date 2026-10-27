"""
Bootstrap the first CMS admin account. Run once, manually, from the
server itself — not exposed as an API endpoint (no public self-registration).

Usage: python3 scripts/create_admin.py
"""
import asyncio
import getpass
import sys

sys.path.insert(0, ".")

from app.auth import hash_password
from app.db.database import create_admin_user, ensure_indexes


async def main():
    await ensure_indexes()

    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords don't match. Aborted.")
        return
    if len(password) < 8:
        print("Password should be at least 8 characters. Aborted.")
        return

    try:
        await create_admin_user(username, hash_password(password))
    except ValueError as exc:
        print(f"Failed: {exc}")
        return

    print(f"Admin '{username}' created successfully.")


if __name__ == "__main__":
    asyncio.run(main())