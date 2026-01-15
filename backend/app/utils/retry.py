# backend/app/utils/retry.py
"""
Retry Utility with Exponential Backoff

Provides robust retry functionality for external API calls with:
- Exponential backoff
- Rate limit (429) handling with Retry-After header support
- Configurable retry conditions
- Logging and metrics
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Tuple, Type, Optional, Any, Union
import random

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: Optional[Exception] = None, attempts: int = 0):
        super().__init__(message)
        self.last_exception = last_exception
        self.attempts = attempts


class RateLimitError(Exception):
    """Raised when API returns 429 rate limit response."""

    def __init__(self, retry_after: float = 60.0, message: str = "Rate limited"):
        super().__init__(message)
        self.retry_after = retry_after


# Default retryable exceptions
DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Try to add httpx exceptions if available
try:
    import httpx
    HTTPX_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.PoolTimeout,
    )
except ImportError:
    HTTPX_RETRYABLE_EXCEPTIONS = ()


def get_retryable_exceptions() -> Tuple[Type[Exception], ...]:
    """Get all retryable exception types."""
    return DEFAULT_RETRYABLE_EXCEPTIONS + HTTPX_RETRYABLE_EXCEPTIONS


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
    operation_name: Optional[str] = None,
) -> Callable:
    """
    Async retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay between retries (default: 60.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        jitter: Add random jitter to prevent thundering herd (default: True)
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Callback function(exception, attempt, delay) called before each retry
        operation_name: Name of operation for logging (defaults to function name)

    Usage:
        @async_retry(max_attempts=3, initial_delay=1.0)
        async def call_external_api():
            ...

        @async_retry(
            max_attempts=5,
            retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError),
            operation_name="elevenlabs_api"
        )
        async def call_elevenlabs():
            ...
    """
    if retryable_exceptions is None:
        retryable_exceptions = get_retryable_exceptions()

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None
            current_delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except RateLimitError as e:
                    # Special handling for rate limits
                    last_exception = e
                    wait_time = min(e.retry_after, max_delay)

                    if attempt < max_attempts:
                        logger.warning(
                            f"[{op_name}] Rate limited (attempt {attempt}/{max_attempts}). "
                            f"Waiting {wait_time:.1f}s before retry..."
                        )
                        if on_retry:
                            on_retry(e, attempt, wait_time)
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[{op_name}] Rate limited after {max_attempts} attempts")

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        # Calculate delay with optional jitter
                        delay = current_delay
                        if jitter:
                            delay = delay * (0.5 + random.random())
                        delay = min(delay, max_delay)

                        logger.warning(
                            f"[{op_name}] Attempt {attempt}/{max_attempts} failed: {type(e).__name__}: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )

                        if on_retry:
                            on_retry(e, attempt, delay)

                        await asyncio.sleep(delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"[{op_name}] Failed after {max_attempts} attempts: {type(e).__name__}: {e}"
                        )

                except Exception as e:
                    # Non-retryable exception - fail immediately
                    logger.error(f"[{op_name}] Non-retryable error: {type(e).__name__}: {e}")
                    raise

            # All retries exhausted
            raise RetryError(
                f"[{op_name}] Failed after {max_attempts} attempts",
                last_exception=last_exception,
                attempts=max_attempts,
            )

        return wrapper

    return decorator


def sync_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
    operation_name: Optional[str] = None,
) -> Callable:
    """
    Synchronous retry decorator with exponential backoff.

    Same parameters as async_retry but for synchronous functions.
    """
    import time

    if retryable_exceptions is None:
        retryable_exceptions = get_retryable_exceptions()

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None
            current_delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except RateLimitError as e:
                    last_exception = e
                    wait_time = min(e.retry_after, max_delay)

                    if attempt < max_attempts:
                        logger.warning(
                            f"[{op_name}] Rate limited (attempt {attempt}/{max_attempts}). "
                            f"Waiting {wait_time:.1f}s..."
                        )
                        if on_retry:
                            on_retry(e, attempt, wait_time)
                        time.sleep(wait_time)
                    else:
                        logger.error(f"[{op_name}] Rate limited after {max_attempts} attempts")

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        delay = current_delay
                        if jitter:
                            delay = delay * (0.5 + random.random())
                        delay = min(delay, max_delay)

                        logger.warning(
                            f"[{op_name}] Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )

                        if on_retry:
                            on_retry(e, attempt, delay)

                        time.sleep(delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(f"[{op_name}] Failed after {max_attempts} attempts: {e}")

                except Exception as e:
                    logger.error(f"[{op_name}] Non-retryable error: {type(e).__name__}: {e}")
                    raise

            raise RetryError(
                f"[{op_name}] Failed after {max_attempts} attempts",
                last_exception=last_exception,
                attempts=max_attempts,
            )

        return wrapper

    return decorator


def check_rate_limit_response(response: Any) -> None:
    """
    Check HTTP response for rate limiting and raise RateLimitError if needed.

    Works with httpx.Response objects. Call this after receiving an API response.

    Usage:
        response = await client.post(url, ...)
        check_rate_limit_response(response)  # Raises RateLimitError if 429
    """
    try:
        if hasattr(response, "status_code") and response.status_code == 429:
            # Try to get Retry-After header
            retry_after = 60.0  # Default
            if hasattr(response, "headers"):
                retry_after_header = response.headers.get("Retry-After", "")
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        pass

            raise RateLimitError(retry_after=retry_after, message="API rate limit exceeded")
    except RateLimitError:
        raise
    except Exception:
        pass  # Not a valid response object


# Pre-configured retry decorators for common use cases

def api_retry() -> Callable:
    """Standard retry for external API calls."""
    return async_retry(
        max_attempts=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        operation_name="api_call",
    )


def elevenlabs_retry() -> Callable:
    """Retry configuration optimized for ElevenLabs API."""
    return async_retry(
        max_attempts=3,
        initial_delay=2.0,
        max_delay=30.0,
        backoff_factor=2.0,
        operation_name="elevenlabs",
    )


def twilio_retry() -> Callable:
    """Retry configuration optimized for Twilio API."""
    return async_retry(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=15.0,
        backoff_factor=2.0,
        operation_name="twilio",
    )


def email_retry() -> Callable:
    """Retry configuration for SMTP/email operations."""
    return async_retry(
        max_attempts=3,
        initial_delay=2.0,
        max_delay=30.0,
        backoff_factor=2.0,
        operation_name="email",
    )


def scraping_retry() -> Callable:
    """Retry configuration for web scraping operations."""
    return async_retry(
        max_attempts=3,
        initial_delay=3.0,
        max_delay=60.0,
        backoff_factor=2.0,
        operation_name="scraping",
    )
