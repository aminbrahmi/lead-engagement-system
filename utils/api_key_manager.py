import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import threading

class APIKeyManager:
    """Manages multiple API keys with rotation and cooldown tracking"""
    
    def __init__(self):
        self.keys: Dict[str, Dict] = {}  # key -> {last_used, cooldown_until, rate_limited}
        self.lock = threading.Lock()
        self._load_keys()
    
    def _load_keys(self):
        """Load all Groq and Google API keys from environment"""
        # Load Groq keys
        groq_keys = []
        for i in range(1, 4):
            key = os.getenv(f"GROQ_API_KEY{i if i > 1 else ''}")
            if key:
                groq_keys.append(key)
        
        # Load Google keys
        google_keys = []
        for i in range(1, 4):
            key = os.getenv(f"GOOGLE_API_KEY{i if i > 1 else ''}")
            if key:
                google_keys.append(key)
        
        # Initialize key tracking
        for key in groq_keys:
            self.keys[key] = {
                "provider": "groq",
                "last_used": None,
                "cooldown_until": None,
                "rate_limited": False,
                "error_count": 0
            }
        
        for key in google_keys:
            self.keys[key] = {
                "provider": "google",
                "last_used": None,
                "cooldown_until": None,
                "rate_limited": False,
                "error_count": 0
            }
        
        print(f"[KeyManager] Loaded {len(groq_keys)} Groq keys, {len(google_keys)} Google keys")
    
    def get_key(self, provider: str) -> Optional[str]:
        """Get an available key for the specified provider"""
        with self.lock:
            available_keys = []
            for key, info in self.keys.items():
                if info["provider"] != provider:
                    continue
                
                # Check if key is rate limited
                if info.get("rate_limited"):
                    if info.get("cooldown_until"):
                        if datetime.now() >= info["cooldown_until"]:
                            # Cooldown expired, reset
                            info["rate_limited"] = False
                            info["cooldown_until"] = None
                            info["error_count"] = 0
                            available_keys.append(key)
                    continue
                
                available_keys.append(key)
            
            if not available_keys:
                # All keys are rate limited, wait for the soonest to recover
                soonest = None
                for key, info in self.keys.items():
                    if info.get("cooldown_until") and (soonest is None or info["cooldown_until"] < soonest):
                        soonest = info["cooldown_until"]
                
                if soonest:
                    wait = (soonest - datetime.now()).total_seconds()
                    if wait > 0:
                        print(f"[KeyManager] All {provider} keys rate limited, waiting {wait:.1f}s...")
                        time.sleep(min(wait, 30))
                        return self.get_key(provider)
                return None
            
            # Return a random available key (round-robin could be better)
            selected = random.choice(available_keys)
            self.keys[selected]["last_used"] = datetime.now()
            return selected
    
    def report_rate_limit(self, key: str, retry_after: Optional[int] = None):
        """Mark a key as rate limited"""
        with self.lock:
            if key in self.keys:
                self.keys[key]["rate_limited"] = True
                self.keys[key]["error_count"] += 1
                
                # Set cooldown
                if retry_after:
                    cooldown = datetime.now() + timedelta(seconds=retry_after + 2)
                else:
                    # Exponential backoff: 30s, 60s, 120s
                    error_count = self.keys[key]["error_count"]
                    cooldown = datetime.now() + timedelta(seconds=min(30 * (2 ** (error_count - 1)), 300))
                
                self.keys[key]["cooldown_until"] = cooldown
                provider = self.keys[key]["provider"]
                print(f"[KeyManager] {provider} key {key[:8]}... rate limited until {cooldown.strftime('%H:%M:%S')}")
    
    def report_success(self, key: str):
        """Reset error count on successful request"""
        with self.lock:
            if key in self.keys:
                self.keys[key]["error_count"] = 0
                self.keys[key]["rate_limited"] = False
                self.keys[key]["cooldown_until"] = None

# Global instance
key_manager = APIKeyManager()