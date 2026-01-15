# backend/app/utils/rate_limit.py
"""
Rate Limiting Utility for API Endpoints

Provides rate limiting functionality using slowapi when available,
with a no-op fallback for development environments.
"""

from functools import wraps
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import slowapi for rate limiting
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    # Create a shared limiter instance
    limiter = Limiter(key_func=get_remote_address)
    RATE_LIMITING_AVAILABLE = True
    logger.info("Rate limiting available (slowapi installed)")
except ImportError:
    limiter = None
    RATE_LIMITING_AVAILABLE = False
    logger.warning("Rate limiting unavailable (slowapi not installed). Run: pip install slowapi")


def get_limiter() -> Optional["Limiter"]:
    """Get the shared limiter instance."""
    return limiter


def rate_limit(limit_string: str) -> Callable:
    """
    Rate limiting decorator that works with or without slowapi.

    Args:
        limit_string: Rate limit string (e.g., "60/minute", "10/hour")

    Usage:
        @rate_limit("60/minute")
        async def my_endpoint(...):
            ...
    """
    if RATE_LIMITING_AVAILABLE and limiter:
        return limiter.limit(limit_string)
    else:
        # No-op decorator when rate limiting is not available
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator


# Pre-configured rate limits for different endpoint types
RATE_LIMITS = {
    "webhook": "120/minute",      # External webhooks (Twilio, ElevenLabs)
    "user_action": "30/minute",   # User-initiated actions (analyze, initiate call)
    "read": "200/minute",         # Read operations (list, get)
    "write": "60/minute",         # Write operations (create, update)
    "expensive": "10/minute",     # Expensive operations (AI analysis)
}


def webhook_rate_limit() -> Callable:
    """Rate limit for external webhooks (Twilio, ElevenLabs)."""
    return rate_limit(RATE_LIMITS["webhook"])


def user_action_rate_limit() -> Callable:
    """Rate limit for user-initiated actions."""
    return rate_limit(RATE_LIMITS["user_action"])


def read_rate_limit() -> Callable:
    """Rate limit for read operations."""
    return rate_limit(RATE_LIMITS["read"])


def write_rate_limit() -> Callable:
    """Rate limit for write operations."""
    return rate_limit(RATE_LIMITS["write"])


def expensive_rate_limit() -> Callable:
    """Rate limit for expensive operations (AI analysis)."""
    return rate_limit(RATE_LIMITS["expensive"])
