# backend/app/utils/circuit_breaker.py
"""
Circuit Breaker Pattern Implementation

Prevents cascading failures by temporarily blocking requests to failing services.
When a service repeatedly fails, the circuit "opens" and requests fail fast
without actually calling the service. After a timeout, it tries again.

States:
- CLOSED: Normal operation, requests go through
- OPEN: Service is failing, requests fail immediately
- HALF_OPEN: Testing if service recovered, limited requests allowed

Use Cases:
- External API calls (Twilio, OpenAI, SMTP)
- Database connections
- Any remote service that might become unavailable

Benefits:
- Prevent wasting resources on requests that will likely fail
- Allow failing services time to recover
- Fail fast and provide better error messages
- Automatic recovery detection
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

from app.utils.logger import logger


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Blocking requests
    HALF_OPEN = "half_open"    # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5           # Failures before opening circuit
    success_threshold: int = 2           # Successes to close from half-open
    timeout: float = 60.0                # Seconds before trying again (open -> half-open)
    half_open_max_calls: int = 3         # Max concurrent calls in half-open state
    name: str = "default"                # Name for logging


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring circuit breaker"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker implementation for protecting against cascading failures.

    Example:
        # Create a circuit breaker for an external service
        breaker = CircuitBreaker(
            name="twilio_api",
            failure_threshold=5,
            timeout=60.0
        )

        @breaker.protect
        async def call_twilio():
            # Your Twilio API call here
            return await twilio_client.make_call(...)

        # Or use as context manager
        async with breaker:
            result = await some_api_call()
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.config = CircuitBreakerConfig(
            name=name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            half_open_max_calls=half_open_max_calls
        )
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        return self.stats.state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.stats.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)"""
        return self.stats.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)"""
        return self.stats.state == CircuitState.HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Function to call (can be sync or async)
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result from the function

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception from the called function
        """
        async with self._lock:
            # Check if we should transition to HALF_OPEN
            if self.stats.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.config.name}' is OPEN. "
                        f"Service is unavailable. Try again in "
                        f"{self._time_until_half_open():.0f}s"
                    )

            # Check if we're in HALF_OPEN and already have max calls
            if self.stats.state == CircuitState.HALF_OPEN:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.config.name}' is HALF_OPEN. "
                        f"Maximum concurrent test calls reached."
                    )
                self.stats.half_open_calls += 1

        # Execute the call
        self.stats.total_calls += 1

        try:
            # Call function (handle both sync and async)
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

        finally:
            if self.stats.state == CircuitState.HALF_OPEN:
                async with self._lock:
                    self.stats.half_open_calls -= 1

    async def _on_success(self):
        """Handle successful call"""
        async with self._lock:
            self.stats.total_successes += 1

            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.success_count += 1
                logger.info(
                    f"[CircuitBreaker:{self.config.name}] Success in HALF_OPEN "
                    f"({self.stats.success_count}/{self.config.success_threshold})"
                )

                if self.stats.success_count >= self.config.success_threshold:
                    self._transition_to_closed()

            elif self.stats.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.stats.failure_count = 0

    async def _on_failure(self, exception: Exception):
        """Handle failed call"""
        async with self._lock:
            self.stats.total_failures += 1
            self.stats.failure_count += 1
            self.stats.last_failure_time = time.time()

            logger.warning(
                f"[CircuitBreaker:{self.config.name}] Failure detected in {self.stats.state.value} state: {exception}"
            )

            if self.stats.state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately opens circuit
                self._transition_to_open()

            elif self.stats.state == CircuitState.CLOSED:
                if self.stats.failure_count >= self.config.failure_threshold:
                    self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try resetting"""
        if self.stats.last_failure_time is None:
            return True

        elapsed = time.time() - self.stats.last_failure_time
        return elapsed >= self.config.timeout

    def _time_until_half_open(self) -> float:
        """Get seconds until circuit can transition to HALF_OPEN"""
        if self.stats.last_failure_time is None:
            return 0.0

        elapsed = time.time() - self.stats.last_failure_time
        remaining = self.config.timeout - elapsed
        return max(0.0, remaining)

    def _transition_to_open(self):
        """Transition circuit to OPEN state"""
        logger.error(
            f"[CircuitBreaker:{self.config.name}] Opening circuit. "
            f"Failure threshold reached ({self.stats.failure_count} failures)"
        )
        self.stats.state = CircuitState.OPEN
        self.stats.last_state_change = time.time()

    def _transition_to_half_open(self):
        """Transition circuit to HALF_OPEN state"""
        logger.info(
            f"[CircuitBreaker:{self.config.name}] Transitioning to HALF_OPEN. "
            f"Testing service recovery..."
        )
        self.stats.state = CircuitState.HALF_OPEN
        self.stats.failure_count = 0
        self.stats.success_count = 0
        self.stats.half_open_calls = 0
        self.stats.last_state_change = time.time()

    def _transition_to_closed(self):
        """Transition circuit to CLOSED state"""
        logger.info(
            f"[CircuitBreaker:{self.config.name}] Closing circuit. "
            f"Service recovered ({self.stats.success_count} successful tests)"
        )
        self.stats.state = CircuitState.CLOSED
        self.stats.failure_count = 0
        self.stats.success_count = 0
        self.stats.last_state_change = time.time()

    def protect(self, func: Callable) -> Callable:
        """
        Decorator to protect a function with this circuit breaker.

        Example:
            breaker = CircuitBreaker(name="api")

            @breaker.protect
            async def fetch_data():
                return await api.get_data()
        """
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                return await self.call(func, *args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                return asyncio.run(self.call(func, *args, **kwargs))
            return sync_wrapper

    async def __aenter__(self):
        """Context manager entry"""
        # Check circuit state but don't execute anything yet
        async with self._lock:
            if self.stats.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.config.name}' is OPEN"
                    )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            await self._on_success()
        else:
            await self._on_failure(exc_val)
        return False

    def get_stats(self) -> dict:
        """Get current statistics as a dictionary"""
        return {
            "name": self.config.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "last_failure_time": self.stats.last_failure_time,
            "time_in_current_state": time.time() - self.stats.last_state_change,
        }

    def reset(self):
        """Manually reset the circuit breaker to CLOSED state"""
        logger.info(f"[CircuitBreaker:{self.config.name}] Manual reset to CLOSED")
        self.stats = CircuitBreakerStats()


# Global circuit breakers for common services
_circuit_breakers = {}


def get_circuit_breaker(name: str, **config) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.

    Example:
        breaker = get_circuit_breaker(
            "twilio",
            failure_threshold=5,
            timeout=60.0
        )
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **config)
    return _circuit_breakers[name]
