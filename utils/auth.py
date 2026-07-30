"""
auth.py — secure authentication helpers: password hashing (bcrypt) + JWT.
"""

import os
import time
import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    # Fail hard rather than fall back to a public default that would let anyone
    # forge valid tokens. Set a strong random JWT_SECRET in .env.
    raise RuntimeError(
        "JWT_SECRET is not set. Generate one (e.g. `python -c \"import secrets; "
        "print(secrets.token_urlsafe(48))\"`) and add it to your .env.")

JWT_ALGO = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 7   # 7 days


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None
