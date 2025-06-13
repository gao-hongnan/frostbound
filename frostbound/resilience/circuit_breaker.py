from __future__ import annotations

import inspect
import logging
import time
from contextlib import contextmanager
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, Generator, Generic, ParamSpec, TypeVar, cast, overload

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Possible states of a circuit breaker."""

    CLOSED = auto()
    """Circuit is closed, requests flow normally"""
    OPEN = auto()
    """Circuit is open, requests are blocked"""
    HALF_OPEN = auto()
    """Circuit is half-open, testing if service is recovered"""


class CircuitBreakerState:
    """
    Tracks the state of a circuit breaker for managing failures.

    Parameters
    ----------
    failure_threshold : int, default=5
        Number of consecutive failures before opening circuit
    reset_timeout_seconds : float, default=30.0
        Time in seconds before attempting to close circuit
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
    ) -> None:
        """
        Initialize a new circuit breaker state.

        Parameters
        ----------
        failure_threshold : int, default=5
            Number of consecutive failures before opening circuit
        reset_timeout_seconds : float, default=30.0
            Time in seconds before attempting to close circuit
        """
        self.failure_count: int = 0
        self.last_failure_time: float = 0
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_threshold: int = failure_threshold
        self.reset_timeout_seconds: float = reset_timeout_seconds

    def record_success(self) -> None:
        """
        Record a successful operation, resetting the failure count.
        """
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """
        Record a failed operation, potentially opening the circuit.

        If the failure count exceeds the threshold, the circuit is opened.
        """
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold and self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} consecutive failures")

    def should_execute(self) -> bool:
        """
        Determine if an operation should be executed based on circuit state.

        Returns
        -------
        bool
            True if the operation should be executed, False otherwise.
        """
        # NOTE: If circuit is closed, always execute
        if self.state == CircuitState.CLOSED:
            return True

        # NOTE: If circuit is open but enough time has passed, allow a test execution
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.reset_timeout_seconds:
            logger.info(f"Circuit breaker allowing test execution after {elapsed:.2f}s")
            self.state = CircuitState.HALF_OPEN
            return True

        # NOTE: If circuit is half-open, allow execution to test recovery
        if self.state == CircuitState.HALF_OPEN:  # noqa: SIM103
            return True

        return False

    @property
    def is_open(self) -> bool:
        """
        Check if the circuit is open.

        Returns
        -------
        bool
            True if the circuit is open, False otherwise.
        """
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """
        Check if the circuit is closed.

        Returns
        -------
        bool
            True if the circuit is closed, False otherwise.
        """
        return self.state == CircuitState.CLOSED

    @property
    def is_half_open(self) -> bool:
        """
        Check if the circuit is half-open.

        Returns
        -------
        bool
            True if the circuit is half-open, False otherwise.
        """
        return self.state == CircuitState.HALF_OPEN


class CircuitBreakerError(Exception):
    """
    Error raised when a circuit breaker is open.

    Parameters
    ----------
    message : str, default="Circuit breaker is open"
        Error message
    """

    def __init__(self, message: str = "Circuit breaker is open") -> None:
        """
        Initialize a new circuit breaker error.

        Parameters
        ----------
        message : str, default="Circuit breaker is open"
            Error message
        """
        self.message = message
        super().__init__(self.message)


class CircuitBreaker(Generic[R]):
    """
    Circuit breaker implementation to prevent cascading failures.

    This class provides a circuit breaker pattern implementation that can be used
    as a decorator or a context manager. Supports both synchronous and asynchronous
    functions.

    Parameters
    ----------
    failure_threshold : int, default=5
        Number of consecutive failures before opening circuit
    reset_timeout_seconds : float, default=30.0
        Time in seconds before attempting to close circuit
    fallback : callable, optional
        Optional fallback function to call when circuit is open
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        fallback: Callable[..., R] | None = None,
    ) -> None:
        """
        Initialize a new circuit breaker.

        Parameters
        ----------
        failure_threshold : int, default=5
            Number of consecutive failures before opening circuit
        reset_timeout_seconds : float, default=30.0
            Time in seconds before attempting to close circuit
        fallback : callable, optional
            Optional fallback function to call when circuit is open
        """
        self.state = CircuitBreakerState(
            failure_threshold=failure_threshold,
            reset_timeout_seconds=reset_timeout_seconds,
        )
        self.fallback = fallback

    @overload
    def __call__(self, func: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def __call__(self, func: Callable[P, Callable[..., R]]) -> Callable[P, Callable[..., R]]: ...

    def __call__(self, func: Callable[P, Any]) -> Callable[P, Any]:
        """
        Decorate a function with circuit breaker functionality.

        Parameters
        ----------
        func : callable
            Function to decorate

        Returns
        -------
        callable
            Decorated function
        """
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return await self.execute_async(func, *args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return self.execute(func, *args, **kwargs)

            return wrapper

    def execute(self, func: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        """
        Execute a function with circuit breaker protection.

        Parameters
        ----------
        func : callable
            Function to execute
        *args : tuple
            Positional arguments
        **kwargs : dict
            Keyword arguments

        Returns
        -------
        Any
            Function result

        Raises
        ------
        CircuitBreakerError
            If circuit is open
        """
        if not self.state.should_execute():
            logger.warning(f"Circuit breaker preventing execution of {func.__name__}")

            if self.fallback:
                logger.info(f"Using fallback for {func.__name__}")
                return self.fallback(*args, **kwargs)

            raise CircuitBreakerError(f"Circuit breaker is open for {func.__name__}")

        try:
            result = func(*args, **kwargs)
            self.state.record_success()
            return result
        except Exception:
            self.state.record_failure()
            raise

    async def execute_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> R:
        """
        Execute an async function with circuit breaker protection.

        Parameters
        ----------
        func : callable
            Async function to execute
        *args : tuple
            Positional arguments
        **kwargs : dict
            Keyword arguments

        Returns
        -------
        Any
            Function result

        Raises
        ------
        CircuitBreakerError
            If circuit is open
        """
        # NOTE: Check if circuit should allow execution
        if not self.state.should_execute():
            logger.warning(f"Circuit breaker preventing execution of {func.__name__}")

            if self.fallback:
                logger.info(f"Using fallback for {func.__name__}")
                if inspect.iscoroutinefunction(self.fallback):
                    return cast(R, await self.fallback(*args, **kwargs))
                return self.fallback(*args, **kwargs)

            raise CircuitBreakerError(f"Circuit breaker is open for {func.__name__}")

        try:
            result = await func(*args, **kwargs)
            self.state.record_success()
            return cast(R, result)
        except Exception:
            self.state.record_failure()
            raise

    @contextmanager
    def context(self) -> Generator[CircuitBreakerState]:
        """
        Context manager for circuit breaker.

        Yields
        ------
        CircuitBreakerState
            The circuit breaker state

        Raises
        ------
        CircuitBreakerError
            If circuit is open
        """
        if not self.state.should_execute():
            logger.warning("Circuit breaker preventing execution in context")
            raise CircuitBreakerError("Circuit breaker is open")

        success = False
        try:
            yield self.state
            success = True
        finally:
            if success:
                self.state.record_success()
            else:
                self.state.record_failure()


def circuit_breaker(
    failure_threshold: int = 5,
    reset_timeout_seconds: float = 30.0,
    fallback: Callable[..., Any] | None = None,
) -> CircuitBreaker[Any]:
    """
    Create a circuit breaker decorator.

    A convenience function to create a circuit breaker with specified parameters.

    Parameters
    ----------
    failure_threshold : int, default=5
        Number of consecutive failures before opening circuit
    reset_timeout_seconds : float, default=30.0
        Time in seconds before attempting to close circuit
    fallback : callable, optional
        Optional fallback function to call when circuit is open

    Returns
    -------
    CircuitBreaker
        CircuitBreaker instance configured with the specified parameters

    Examples
    --------
    >>> @circuit_breaker(failure_threshold=3)
    ... def my_function():
    ...     # Function implementation
    ...     pass

    >>> @circuit_breaker(fallback=lambda: "fallback value")
    ... async def my_async_function():
    ...     # Async function implementation
    ...     pass
    """
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        reset_timeout_seconds=reset_timeout_seconds,
        fallback=fallback,
    )
