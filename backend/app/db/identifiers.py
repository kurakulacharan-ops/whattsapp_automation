"""SQL document IDs compatible with existing 24-hex attendance IDs."""

import re
import secrets
import time


def new_record_id() -> str:
    # Retain timestamp ordering and the existing URL/database ID length.
    return f"{int(time.time()):08x}" + secrets.token_hex(8)


def parse_record_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{24}", value) is None:
        raise ValueError("Invalid attendance record ID")
    return value.lower()
