# backend/app/utils/retry_logic.py
"""
Retry Logic with Exponential Backoff

This module provides decorators and utilities for retrying failed operations
with intelligent backoff strategies.

Use Cases:
- API calls to external services (Twilio, OpenAI, SMTP)
- Database operations that might fail due to transient issues
- Network requests that might timeout

Features:
- Exponential backoff with jitter
- Configurable max retries
- Selective exception handling
- Async support
"""

import asyncio
import functools
import random
import time
from typing import Callable, Optional, Type, Tuple, Any

from app.utils.logger import logger


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
) -> float:
    """
    Calculate backoff delay using exponential backoff with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation (typically 2.0)
        jitter: Whether to add random jitter to prevent thundering herd

    Returns:
        float: Delay in seconds before next retry
    """
    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = min(base_delay * (exponential_base ** attempt), max_delay)

    # Add jitter (random factor between 0.5 and 1.5) to prevent thundering herd
    if jitter:
        delay *= (0.5 + random.random())

    return delay


def retry_sync(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for synchronous functions to add retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback called on each retry with (exception, attempt)

    Example:
        @retry_sync(max_retries=3, base_delay=1.0)
        def flaky_api_call():
            response = requests.get("https://api.example.com/data")
            response.raise_for_status()
            return response.json()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    delay = calculate_backoff(attempt, base_delay, max_delay)
                    logger.warning(
                        f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        try:
                            on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"[Retry] on_retry callback failed: {callback_error}")

                    time.sleep(delay)

            # Should never reach here, but just in case
            raise last_exception

        return wrapper
    return decorator


def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], Any]] = None
):
    """
    Decorator for async functions to add retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional async callback called on each retry with (exception, attempt)

    Example:
        @retry_async(max_retries=3, base_delay=1.0, exceptions=(httpx.HTTPError,))
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                response = await client.get("https://api.example.com/data")
                response.raise_for_status()
                return response.json()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    delay = calculate_backoff(attempt, base_delay, max_delay)
                    logger.warning(
                        f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        try:
                            if asyncio.iscoroutinefunction(on_retry):
                                await on_retry(e, attempt)
                            else:
                                on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"[Retry] on_retry callback failed: {callback_error}")

                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            raise last_exception

        return wrapper
    return decorator


class RetryableOperation:
    """
    Context manager for retryable operations (non-decorator approach).

    Example:
        async with RetryableOperation(max_retries=3) as retry:
            while retry.should_retry():
                try:
                    result = await some_api_call()
                    retry.success(result)
                except SomeError as e:
                    retry.failure(e)

            return retry.result
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt = 0
        self.result = None
        self.last_exception = None
        self._success = False

    def should_retry(self) -> bool:
        """Check if we should attempt/retry the operation"""
        return not self._success and self.attempt <= self.max_retries

    def success(self, result: Any = None):
        """Mark operation as successful"""
        self._success = True
        self.result = result

    def failure(self, exception: Exception):
        """Mark operation as failed"""
        self.last_exception = exception
        self.attempt += 1

    async def wait(self):
        """Wait before next retry (with exponential backoff)"""
        if self.attempt > 0 and self.attempt <= self.max_retries:
            delay = calculate_backoff(self.attempt - 1, self.base_delay, self.max_delay)
            logger.warning(
                f"[Retry] Operation failed (attempt {self.attempt}/{self.max_retries + 1}): "
                f"{self.last_exception}. Retrying in {delay:.2f}s..."
            )
            await asyncio.sleep(delay)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._success and self.last_exception:
            logger.error(
                f"[Retry] Operation failed after {self.attempt} attempts: {self.last_exception}"
            )
            raise self.last_exception
        return False
