# tools/key_rotator.py
# Rotates across multiple API keys to avoid per-key rate limits.
# Supports Groq (3 keys) and Google (3 keys).
# Usage: from tools.key_rotator import groq_key, google_key

import os
import time
import threading
from dotenv import load_dotenv
load_dotenv()

class KeyRotator:
    """
    Round-robin key rotator with per-key cooldown tracking.
    When a key hits a rate limit, it's cooled down for `cooldown_seconds`
    before being used again. Other keys are tried in the meantime.
    """

    def __init__(self, keys: list[str], cooldown_seconds: int = 60):
        self._keys      = [k for k in keys if k]  # filter out None/empty
        self._cooldowns = {}                        # key → available_at timestamp
        self._index     = 0
        self._lock      = threading.Lock()
        self.cooldown   = cooldown_seconds

        if not self._keys:
            raise ValueError("No API keys provided to KeyRotator")

        print(f"[KeyRotator] Loaded {len(self._keys)} keys")

    def get(self) -> str:
        """Returns the next available key, waiting if all are in cooldown."""
        with self._lock:
            now = time.time()

            # Try each key in round-robin order
            for _ in range(len(self._keys)):
                key = self._keys[self._index % len(self._keys)]
                self._index += 1

                available_at = self._cooldowns.get(key, 0)
                if now >= available_at:
                    return key

            # All keys are in cooldown — find the one that recovers soonest
            soonest_key = min(self._keys, key=lambda k: self._cooldowns.get(k, 0))
            wait = max(0, self._cooldowns[soonest_key] - time.time())
            if wait > 0:
                print(f"[KeyRotator] All keys in cooldown. Waiting {wait:.1f}s...")
                time.sleep(wait + 0.5)
            return soonest_key

    def mark_rate_limited(self, key: str):
        """Call this when a key returns a 429 / rate limit error."""
        with self._lock:
            self._cooldowns[key] = time.time() + self.cooldown
            print(f"[KeyRotator] Key ...{key[-6:]} rate limited — cooling {self.cooldown}s")

    def __len__(self):
        return len(self._keys)


# ── Singleton rotators ───────────────────────────────────────────────────────

_groq_rotator = KeyRotator(
    keys=[
        os.getenv("GROQ_API_KEY",  ""),
        os.getenv("GROQ_API_KEY1", ""),
        os.getenv("GROQ_API_KEY2", ""),
    ],
    cooldown_seconds=62  # Groq TPM resets every 60s — add 2s buffer
)

_google_rotator = KeyRotator(
    keys=[
        os.getenv("GOOGLE_API_KEY",  ""),
        os.getenv("GOOGLE_API_KEY1", ""),
        os.getenv("GOOGLE_API_KEY2", ""),
    ],
    cooldown_seconds=62
)


def groq_key() -> str:
    """Get the next available Groq API key."""
    return _groq_rotator.get()

def google_key() -> str:
    """Get the next available Google API key."""
    return _google_rotator.get()

def mark_groq_limited(key: str):
    """Mark a Groq key as rate-limited."""
    _groq_rotator.mark_rate_limited(key)

def mark_google_limited(key: str):
    """Mark a Google key as rate-limited."""
    _google_rotator.mark_rate_limited(key)