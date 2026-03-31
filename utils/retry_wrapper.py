import time
import asyncio
from functools import wraps
from typing import TypeVar, Callable, Any
from utils.api_key_manager import key_manager

T = TypeVar('T')

def with_key_rotation(provider: str, fallback_providers: list = None):
    """Decorator for API calls with key rotation"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            max_attempts = 3
            last_error = None
            
            for attempt in range(max_attempts):
                # Get a fresh key
                api_key = key_manager.get_key(provider)
                if not api_key:
                    print(f"[Wrapper] No available {provider} keys, waiting...")
                    time.sleep(10)
                    continue
                
                try:
                    # Add key to kwargs
                    kwargs['api_key'] = api_key
                    result = func(*args, **kwargs)
                    key_manager.report_success(api_key)
                    return result
                except Exception as e:
                    error_msg = str(e).lower()
                    last_error = e
                    
                    # Check if it's a rate limit error
                    if any(k in error_msg for k in ["rate_limit", "429", "resource_exhausted"]):
                        # Extract retry-after if available
                        retry_after = None
                        if hasattr(e, 'response'):
                            retry_after = e.response.headers.get('Retry-After')
                            if retry_after:
                                retry_after = int(retry_after)
                        
                        key_manager.report_rate_limit(api_key, retry_after)
                        wait = retry_after if retry_after else (attempt + 1) * 30
                        print(f"[Wrapper] {provider} rate limited, key rotated. Waiting {wait}s...")
                        time.sleep(min(wait, 60))
                    else:
                        print(f"[Wrapper] Error with {provider} key {api_key[:8]}...: {e}")
                        # Non-rate-limit error, try another key immediately
                        continue
            
            # All attempts failed
            if fallback_providers:
                # Try fallback providers
                for fallback in fallback_providers:
                    try:
                        kwargs['api_key'] = key_manager.get_key(fallback)
                        return func(*args, **kwargs)
                    except:
                        continue
            
            raise last_error or Exception(f"No working {provider} keys")
        
        return wrapper
    return decorator