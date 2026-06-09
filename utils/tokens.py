"""
tokens.py — secure, signed tokens for opt-out / opt-in links (RGPD).

Unsubscribe and resubscribe links must not be forgeable: a guessable token
would let anyone unsubscribe — or worse, re-subscribe — a third party who
opted out (which would cause an unlawful re-contact under GDPR Art. 21/7§3).

We sign the lead_id with HMAC-SHA256 using a server-side secret. Validation
uses a constant-time comparison to avoid timing attacks.

Set UNSUB_SECRET in the environment (.env) to a long random string.
"""

import os
import hmac
import hashlib

from dotenv import load_dotenv

load_dotenv()


def _secret() -> bytes:
    secret = os.getenv("UNSUB_SECRET", "")
    if not secret:
        # Fallback keeps the app working in dev, but logs a clear warning.
        # In production UNSUB_SECRET MUST be set to a strong random value.
        print("[Tokens] ⚠ UNSUB_SECRET not set — using insecure default. "
              "Set UNSUB_SECRET in .env for production.")
        secret = "leadflow-insecure-default-change-me"
    return secret.encode()


def make_token(lead_id: str, purpose: str = "unsub") -> str:
    """Generate a signed token for a given lead and purpose."""
    msg = f"{purpose}:{lead_id}".encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:32]


def verify_token(lead_id: str, token: str, purpose: str = "unsub") -> bool:
    """Constant-time verification of a token."""
    if not token:
        return False
    expected = make_token(lead_id, purpose)
    return hmac.compare_digest(expected, token)
