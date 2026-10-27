"""
Webhook signature verification.

CONFIRMED against Interakt's actual docs (resource-center/interakts-webhooks-
for-customer-messages-sent-template-status): header is "Interakt-Signature",
containing a hex-encoded HMAC-SHA256 signature of the raw request body,
PREFIXED with "sha256=". Their own sample code:

    return "sha256=" + BitConverter.ToString(hmac.ComputeHash(bytes))...ToLower();

This is no longer a best-effort guess — implementation below matches their
documented format exactly.
"""
import hashlib
import hmac

from app.config import settings


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify that an incoming webhook genuinely came from Interakt.

    Args:
        raw_body: the exact raw request bytes (must be unparsed — signature
                   is computed over raw bytes, not the re-serialized JSON)
        signature_header: value of the Interakt-Signature header, including
                   the "sha256=" prefix (e.g. "sha256=b84783d1...")

    Returns:
        True if signature is valid, False otherwise.
    """
    if not settings.interakt_webhook_secret:
        return False

    if not signature_header.startswith("sha256="):
        return False

    received_hex = signature_header[len("sha256="):]

    expected_hex = hmac.new(
        key=settings.interakt_webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hex, received_hex)