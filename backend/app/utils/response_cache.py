# backend/app/utils/response_cache.py
"""
In-memory response cache for low-latency voice agent responses.
Caches LLM responses by state + lead context to avoid repeated API calls.
"""

import hashlib
import time
from typing import Dict, Optional, Tuple
from app.utils.logger import logger


class ResponseCache:
    """
    Simple in-memory cache for agent responses.
    Key format: f"{state_id}_{lead_id}_{hash(user_input)}"
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with optional TTL."""
        self.cache: Dict[str, Tuple[str, float]] = {}
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _make_key(self, state_id: int, lead_id: int, user_input: str) -> str:
        """Generate cache key from state, lead, and user input."""
        # Hash user input to keep key manageable
        input_hash = hashlib.md5(user_input.lower().strip().encode()).hexdigest()[:8]
        return f"{state_id}_{lead_id}_{input_hash}"

    def get(self, state_id: int, lead_id: int, user_input: str) -> Optional[str]:
        """Get cached response if exists and not expired."""
        key = self._make_key(state_id, lead_id, user_input)

        if key not in self.cache:
            self.misses += 1
            return None

        response, timestamp = self.cache[key]

        # Check TTL
        if time.time() - timestamp > self.ttl_seconds:
            del self.cache[key]
            self.misses += 1
            return None

        self.hits += 1
        logger.info(f"[CACHE] Hit: {key}")
        return response

    def set(self, state_id: int, lead_id: int, user_input: str, response: str) -> None:
        """Cache a response."""
        key = self._make_key(state_id, lead_id, user_input)
        self.cache[key] = (response, time.time())
        logger.info(f"[CACHE] Set: {key} ({len(response)} chars)")

    def get_stats(self) -> Dict:
        """Return cache hit/miss statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total": total,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_size": len(self.cache),
        }

    def clear(self) -> None:
        """Clear entire cache."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


# Global cache instance
_response_cache = ResponseCache(ttl_seconds=3600)  # 1 hour TTL


def get_response_cache() -> ResponseCache:
    """Get the global response cache instance."""
    return _response_cache
