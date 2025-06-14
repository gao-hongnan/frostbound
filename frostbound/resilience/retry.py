from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import random
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    AsyncContextManager,
    ContextManager,
    Generic,
    Literal,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
    final,
    overload,
    runtime_checkable,
)

P = ParamSpec("P")
P1 = ParamSpec("P1")
P2 = ParamSpec("P2")
R = TypeVar("R")
R1 = TypeVar("R1")
R2 = TypeVar("R2")
E = TypeVar("E", bound=Exception)
T = TypeVar("T")
SyncFn = TypeVar("SyncFn", bound=Callable[..., object])
AsyncFn = TypeVar("AsyncFn", bound=Callable[..., Awaitable[object]])

logger = logging.getLogger(__name__)


class RetryOutcome(str, Enum):
    """
    Possible outcomes of a retry operation with string representations.

    Attributes
    ----------
    SUCCESS : str
        Operation succeeded.
    FAILURE : str
        Operation failed.
    EXHAUSTED : str
        All retries were exhausted.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    EXHAUSTED = "exhausted"

    def __str__(self) -> str:
        return self.value


@dataclass
class Statistics:
    """
    Performance statistics for retry operations.

    Attributes
    ----------
    attempts : int
        Number of attempts made.
    total_delay : float
        Total time spent waiting between retries.
    start_time : float
        Timestamp when retry operation started.
    execution_times : list[float]
        List of execution times for each attempt.
    """

    attempts: int = 0
    total_delay: float = 0.0
    start_time: float = field(default_factory=time.time)
    execution_times: list[float] = field(default_factory=list)

    @property
    def elapsed_time(self) -> float:
        """
        Total elapsed time since the start of the retry operation.

        Returns
        -------
        float
            Elapsed time in seconds.
        """
        return time.time() - self.start_time

    @property
    def average_execution_time(self) -> float:
        """
        Average execution time of attempts.

        Returns
        -------
        float
            Average execution time in seconds, or 0.0 if no attempts.
        """
        return sum(self.execution_times) / len(self.execution_times) if self.execution_times else 0.0


@dataclass
class RetryState(Generic[R, E]):
    """
    Comprehensive state tracking for retry operations.

    Parameters
    ----------
    statistics : Statistics
        Performance statistics for the retry operation.
    last_exception : E or None
        The last exception that occurred during retry.
    last_result : R or None
        The last result from a successful execution.
    outcome : RetryOutcome or None
        The final outcome of the retry operation.

    Attributes
    ----------
    statistics : Statistics
        Performance statistics for the retry operation.
    last_exception : E or None
        The last exception that occurred during retry.
    last_result : R or None
        The last result from a successful execution.
    outcome : RetryOutcome or None
        The final outcome of the retry operation.
    """

    @staticmethod
    def convert_type(
        state: RetryState[object, Exception],
    ) -> RetryState[object, Exception]:
        """
        Helper method for type casting.

        Parameters
        ----------
        state : RetryState[object, Exception]
            State to convert.

        Returns
        -------
        RetryState[object, Exception]
            The same state object.
        """
        return state

    statistics: Statistics = field(default_factory=Statistics)
    last_exception: E | None = None
    last_result: R | None = None
    outcome: RetryOutcome | None = None

    @property
    def attempts(self) -> int:
        """
        Current number of attempts.

        Returns
        -------
        int
            Number of attempts made so far.
        """
        return self.statistics.attempts

    @property
    def elapsed_time(self) -> float:
        """
        Total elapsed time since the start of retry operations.

        Returns
        -------
        float
            Elapsed time in seconds.
        """
        return self.statistics.elapsed_time


@runtime_checkable
class RetryPredicate(Protocol):
    """
    Protocol for determining if a retry should be attempted.

    Methods
    -------
    __call__(state: RetryState[object, Exception]) -> bool
        Determine if retry should be attempted based on the current state.
    """

    def __call__(self, state: RetryState[object, Exception]) -> bool: ...


@runtime_checkable
class WaitStrategy(Protocol):
    """
    Protocol for determining wait time between retries.

    Methods
    -------
    __call__(state: RetryState[object, Exception]) -> float
        Calculate delay time before next retry attempt.
    """

    def __call__(self, state: RetryState[object, Exception]) -> float: ...


@runtime_checkable
class StopStrategy(Protocol):
    """
    Protocol for determining when to stop retrying.

    Methods
    -------
    __call__(state: RetryState[object, Exception]) -> bool
        Determine if retry attempts should stop.
    """

    def __call__(self, state: RetryState[object, Exception]) -> bool: ...


@runtime_checkable
class BeforeCallHook(Protocol):
    """
    Hook executed before a retry attempt.

    Methods
    -------
    __call__(state: RetryState[object, Exception], *args: object, **kwargs: object) -> None
        Execute hook before a retry attempt.
    """

    def __call__(self, state: RetryState[object, Exception], *args: object, **kwargs: object) -> None: ...


@runtime_checkable
class AfterCallHook(Protocol[R, E]):
    """
    Hook executed after a retry attempt.

    Methods
    -------
    __call__(state: RetryState[R, E], outcome: Literal["success", "failure"], result: R | None = None, exception: E | None = None) -> None
        Execute hook after a retry attempt with the outcome.
    """

    def __call__(
        self,
        state: RetryState[R, E],
        outcome: Literal["success", "failure"],
        result: R | None = None,
        exception: E | None = None,
    ) -> None: ...


class RetryIfException(Generic[E]):
    """
    Retry if a specific exception type is raised.

    Parameters
    ----------
    *exception_types : type[E]
        Exception types that should trigger retry.
    exclude : list[type[Exception]] or None, optional
        Exception types that should never trigger retry even if they
        inherit from the specified exception_types.

    Notes
    -----
    If no exception_types are provided, defaults to retrying on all exceptions.
    """

    def __init__(self, *exception_types: type[E], exclude: list[type[Exception]] | None = None):
        """
        Initialize retry condition for specific exception types.

        Parameters
        ----------
        *exception_types : type[E]
            Exception types that should trigger retry.
        exclude : list[type[Exception]] or None, optional
            Exception types that should never trigger retry even if they
            inherit from the specified exception_types.
        """
        self.exception_types = exception_types or (Exception,)
        self.exclude_types = exclude or []

    def __call__(self, state: RetryState[object, E]) -> bool:
        """
        Check if exception should trigger retry.

        Parameters
        ----------
        state : RetryState[object, E]
            Current retry state.

        Returns
        -------
        bool
            True if exception should trigger retry, False otherwise.
        """
        if not state.last_exception:
            return False

        for exclude_type in self.exclude_types:
            if isinstance(state.last_exception, exclude_type):
                return False

        return isinstance(state.last_exception, self.exception_types)


class RetryIfResult:
    """
    Retry based on the function's return value.

    Parameters
    ----------
    predicate : Callable[[object], bool]
        Function that returns True if result should trigger retry.
    """

    def __init__(self, predicate: Callable[[object], bool]):
        """
        Initialize retry condition based on result.

        Parameters
        ----------
        predicate : Callable[[object], bool]
            Function that returns True if result should trigger retry.
        """
        self.predicate = predicate

    def __call__(self, state: RetryState[object, Exception]) -> bool:
        """
        Check if result should trigger retry.

        Parameters
        ----------
        state : RetryState[object, Exception]
            Current retry state.

        Returns
        -------
        bool
            True if result should trigger retry, False otherwise.
        """
        return state.last_exception is None and state.last_result is not None and self.predicate(state.last_result)


class ExponentialBackoff:
    """
    Exponential backoff with jitter for retry delays.

    Parameters
    ----------
    base_delay : float, optional
        Initial delay in seconds. Default is 0.1.
    max_delay : float, optional
        Maximum delay in seconds. Default is 10.0.
    multiplier : float, optional
        Multiplier for increasing delay between retries. Default is 2.0.
    jitter : float, optional
        Random factor to add variation to delay (0-1). Default is 0.1.
    """

    def __init__(
        self,
        base_delay: float = 0.1,
        max_delay: float = 10.0,
        multiplier: float = 2.0,
        jitter: float = 0.1,
    ):
        """
        Initialize exponential backoff strategy.

        Parameters
        ----------
        base_delay : float, optional
            Initial delay in seconds. Default is 0.1.
        max_delay : float, optional
            Maximum delay in seconds. Default is 10.0.
        multiplier : float, optional
            Multiplier for increasing delay between retries. Default is 2.0.
        jitter : float, optional
            Random factor to add variation to delay (0-1). Default is 0.1.
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def __call__(self, state: RetryState[object, Exception]) -> float:
        """
        Calculate delay with exponential backoff and jitter.

        Parameters
        ----------
        state : RetryState[object, Exception]
            Current retry state.

        Returns
        -------
        float
            Delay in seconds before next retry.
        """
        attempt = max(1, state.attempts)
        delay = min(self.max_delay, self.base_delay * (self.multiplier ** (attempt - 1)))

        if self.jitter > 0:
            delay = random.uniform(0, delay * (1 + self.jitter))

        return delay


class StopAfterAttempt:
    """
    Stop retrying after a specified number of attempts.

    Parameters
    ----------
    max_attempts : int
        Maximum number of attempts including the initial.

    Raises
    ------
    ValueError
        If max_attempts is less than 1.
    """

    def __init__(self, max_attempts: int):
        """
        Initialize stop condition based on attempts.

        Parameters
        ----------
        max_attempts : int
            Maximum number of attempts including the initial.

        Raises
        ------
        ValueError
            If max_attempts is less than 1.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts

    def __call__(self, state: RetryState[object, Exception]) -> bool:
        """
        Check if maximum attempts reached.

        Parameters
        ----------
        state : RetryState[object, Exception]
            Current retry state.

        Returns
        -------
        bool
            True if should stop retrying, False otherwise.
        """
        return state.attempts >= self.max_attempts


class StopAfterDelay:
    """
    Stop retrying after a specified time delay.

    Parameters
    ----------
    max_delay_seconds : float
        Maximum elapsed time in seconds.

    Raises
    ------
    ValueError
        If max_delay_seconds is not positive.
    """

    def __init__(self, max_delay_seconds: float):
        """
        Initialize stop condition based on elapsed time.

        Parameters
        ----------
        max_delay_seconds : float
            Maximum elapsed time in seconds.

        Raises
        ------
        ValueError
            If max_delay_seconds is not positive.
        """
        if max_delay_seconds <= 0:
            raise ValueError("max_delay_seconds must be positive")
        self.max_delay_seconds = max_delay_seconds

    def __call__(self, state: RetryState[object, Exception]) -> bool:
        """
        Check if maximum delay reached.

        Parameters
        ----------
        state : RetryState[object, Exception]
            Current retry state.

        Returns
        -------
        bool
            True if should stop retrying, False otherwise.
        """
        return state.elapsed_time >= self.max_delay_seconds


@final
class RetryPolicy:
    """
    Comprehensive policy for configuring retry behavior.

    This class encapsulates all retry logic and conditions.

    Parameters
    ----------
    retry_on : Sequence[RetryPredicate] or None, optional
        Conditions that determine if retry should be attempted.
    stop : Sequence[StopStrategy] or None, optional
        Conditions that determine when to stop retrying.
    wait : WaitStrategy or None, optional
        Strategy for determining wait time between retries.
    before_hooks : Sequence[BeforeCallHook] or None, optional
        Hooks to execute before each attempt.
    after_hooks : Sequence[AfterCallHook[object, Exception]] or None, optional
        Hooks to execute after each attempt.
    reraise : bool, optional
        Whether to reraise last exception after retries exhausted. Default is True.
    retry_error_cls : type[Exception] or None, optional
        Custom exception class to wrap original exception.
    logger : logging.Logger or None, optional
        Logger to use for retry operations.
    """

    def __init__(
        self,
        retry_on: Sequence[RetryPredicate] | None = None,
        stop: Sequence[StopStrategy] | None = None,
        wait: WaitStrategy | None = None,
        before_hooks: Sequence[BeforeCallHook] | None = None,
        after_hooks: Sequence[AfterCallHook[object, Exception]] | None = None,
        reraise: bool = True,
        retry_error_cls: type[Exception] | None = None,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize retry policy.

        Parameters
        ----------
        retry_on : Sequence[RetryPredicate] or None, optional
            Conditions that determine if retry should be attempted.
        stop : Sequence[StopStrategy] or None, optional
            Conditions that determine when to stop retrying.
        wait : WaitStrategy or None, optional
            Strategy for determining wait time between retries.
        before_hooks : Sequence[BeforeCallHook] or None, optional
            Hooks to execute before each attempt.
        after_hooks : Sequence[AfterCallHook[object, Exception]] or None, optional
            Hooks to execute after each attempt.
        reraise : bool, optional
            Whether to reraise last exception after retries exhausted. Default is True.
        retry_error_cls : type[Exception] or None, optional
            Custom exception class to wrap original exception.
        logger : logging.Logger or None, optional
            Logger to use for retry operations.
        """
        self.retry_conditions = retry_on or [RetryIfException()]
        self.stop_conditions = stop or [StopAfterAttempt(3)]
        self.wait_strategy = wait or ExponentialBackoff()
        self.before_hooks = before_hooks or []
        self.after_hooks = after_hooks or []
        self.reraise = reraise
        self.retry_error_cls = retry_error_cls or RetryError
        self.logger = logger or logging.getLogger("retry")

    @classmethod
    def default(cls) -> RetryPolicy:
        """
        Create a default retry policy.

        Returns
        -------
        RetryPolicy
            Default retry policy configuration.
        """
        return cls()

    @classmethod
    def with_max_attempts(cls, max_attempts: int) -> RetryPolicy:
        """
        Create a retry policy with specified maximum attempts.

        Parameters
        ----------
        max_attempts : int
            Maximum number of attempts.

        Returns
        -------
        RetryPolicy
            Configured retry policy.
        """
        return cls(stop=[StopAfterAttempt(max_attempts)])

    @classmethod
    def with_max_delay(cls, max_delay_seconds: float) -> RetryPolicy:
        """
        Create a retry policy with specified maximum delay.

        Parameters
        ----------
        max_delay_seconds : float
            Maximum time in seconds for retry operations.

        Returns
        -------
        RetryPolicy
            Configured retry policy.
        """
        return cls(stop=[StopAfterDelay(max_delay_seconds)])

    @classmethod
    def exponential_backoff(
        cls,
        max_attempts: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 10.0,
        multiplier: float = 2.0,
        jitter: float = 0.1,
    ) -> RetryPolicy:
        """
        Create a retry policy with exponential backoff.

        Parameters
        ----------
        max_attempts : int, optional
            Maximum number of attempts. Default is 3.
        base_delay : float, optional
            Initial delay in seconds. Default is 0.1.
        max_delay : float, optional
            Maximum delay in seconds. Default is 10.0.
        multiplier : float, optional
            Multiplier for increasing delay between retries. Default is 2.0.
        jitter : float, optional
            Random factor to add variation to delay (0-1). Default is 0.1.

        Returns
        -------
        RetryPolicy
            Configured retry policy with exponential backoff.
        """
        return cls(
            stop=[StopAfterAttempt(max_attempts)],
            wait=ExponentialBackoff(
                base_delay=base_delay,
                max_delay=max_delay,
                multiplier=multiplier,
                jitter=jitter,
            ),
        )

    def should_retry(self, state: RetryState[R, E]) -> bool:
        """
        Determine if retry should be attempted based on current state.

        Parameters
        ----------
        state : RetryState[R, E]
            Current retry state.

        Returns
        -------
        bool
            True if retry should be attempted, False otherwise.
        """
        for condition in self.stop_conditions:
            if condition(cast(RetryState[object, Exception], state)):
                return False

        return any(condition(cast(RetryState[object, Exception], state)) for condition in self.retry_conditions)

    def get_wait_time(self, state: RetryState[R, E]) -> float:
        """
        Get wait time for next retry attempt.

        Parameters
        ----------
        state : RetryState[R, E]
            Current retry state.

        Returns
        -------
        float
            Wait time in seconds.
        """
        return self.wait_strategy(cast(RetryState[object, Exception], state))

    def execute_before_hooks(self, state: RetryState[R, E], *args: object, **kwargs: object) -> None:
        """
        Execute all before hooks.

        Parameters
        ----------
        state : RetryState[R, E]
            Current retry state.
        *args : object
            Function arguments.
        **kwargs : object
            Function keyword arguments.
        """
        for hook in self.before_hooks:
            try:
                state_for_hook = cast(RetryState[object, Exception], state)
                hook(state_for_hook, *args, **kwargs)
            except Exception as e:
                self.logger.warning(f"Error in before hook: {e}")

    def execute_after_hooks(
        self,
        state: RetryState[R, E],
        outcome: Literal["success", "failure"],
        result: R | None = None,
        exception: E | None = None,
    ) -> None:
        """
        Execute all after hooks.

        Parameters
        ----------
        state : RetryState[R, E]
            Current retry state.
        outcome : Literal["success", "failure"]
            Outcome of the attempt.
        result : R or None, optional
            Function result if successful.
        exception : E or None, optional
            Exception if failed.
        """
        for hook in self.after_hooks:
            try:
                state_for_hook = cast(RetryState[object, Exception], state)
                hook(state_for_hook, outcome, result, exception)
            except Exception as e:
                self.logger.warning(f"Error in after hook: {e}")


class RetryError(Exception):
    """
    Exception raised when all retry attempts are exhausted.

    Parameters
    ----------
    state : RetryState[R, E]
        Final retry state.

    Attributes
    ----------
    state : RetryState[R, E]
        Final retry state.
    last_exception : E or None
        The last exception that occurred during retry.
    """

    def __init__(self, state: RetryState[R, E]):
        """
        Initialize retry error.

        Parameters
        ----------
        state : RetryState[R, E]
            Final retry state.
        """
        self.state = state
        self.last_exception = state.last_exception

        message = f"All {state.attempts} retry attempts failed over {state.elapsed_time:.2f} seconds"

        if state.last_exception:
            message += f": {type(state.last_exception).__name__}: {state.last_exception}"

        super().__init__(message)


class Retry(Generic[R, E]):
    """
    Comprehensive retry functionality for both sync and async operations.

    This class provides multiple usage patterns:
    - As a function decorator
    - As a context manager
    - As a direct callable

    It handles both synchronous and asynchronous code automatically.

    Parameters
    ----------
    policy : RetryPolicy or None, optional
        Complete retry policy (takes precedence over other parameters).
    max_attempts : int or None, optional
        Maximum number of attempts (if no policy provided).
    base_delay : float or None, optional
        Initial delay in seconds (if no policy provided).
    max_delay : float or None, optional
        Maximum delay in seconds (if no policy provided).
    multiplier : float or None, optional
        Backoff multiplier (if no policy provided).
    jitter : float or None, optional
        Random jitter factor (if no policy provided).
    retry_on_exceptions : list[type[Exception]] or None, optional
        Exception types to retry on (if no policy provided).
    retry_on_result : Callable[[object], bool] or None, optional
        Function to determine if result should trigger retry.
    stop_after_delay : float or None, optional
        Maximum total time for retrying in seconds.
    reraise : bool, optional
        Whether to reraise original exception after retries exhausted. Default is True.

    Attributes
    ----------
    policy : RetryPolicy
        The retry policy to use.
    """

    _fn: Callable[..., R] | None
    _async_fn: Callable[..., Awaitable[R]] | None

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        max_attempts: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        multiplier: float | None = None,
        jitter: float | None = None,
        retry_on_exceptions: list[type[Exception]] | None = None,
        retry_on_result: Callable[[object], bool] | None = None,
        stop_after_delay: float | None = None,
        reraise: bool = True,
    ):
        """
        Initialize retry instance.

        Parameters
        ----------
        policy : RetryPolicy or None, optional
            Complete retry policy (takes precedence over other parameters).
        max_attempts : int or None, optional
            Maximum number of attempts (if no policy provided).
        base_delay : float or None, optional
            Initial delay in seconds (if no policy provided).
        max_delay : float or None, optional
            Maximum delay in seconds (if no policy provided).
        multiplier : float or None, optional
            Backoff multiplier (if no policy provided).
        jitter : float or None, optional
            Random jitter factor (if no policy provided).
        retry_on_exceptions : list[type[Exception]] or None, optional
            Exception types to retry on (if no policy provided).
        retry_on_result : Callable[[object], bool] or None, optional
            Function to determine if result should trigger retry.
        stop_after_delay : float or None, optional
            Maximum total time for retrying in seconds.
        reraise : bool, optional
            Whether to reraise original exception after retries exhausted. Default is True.
        """
        self._fn = None
        self._async_fn = None

        if policy is not None:
            self.policy = policy
        else:
            retry_conditions: list[RetryPredicate] = []
            stop_conditions: list[StopStrategy] = []

            if retry_on_exceptions:
                retry_conditions.append(RetryIfException(*retry_on_exceptions))
            else:
                # NOTE: Default retry on common transient exceptions
                retry_conditions.append(RetryIfException(ConnectionError, TimeoutError, OSError))

            if retry_on_result:
                retry_conditions.append(RetryIfResult(retry_on_result))

            if max_attempts:
                stop_conditions.append(StopAfterAttempt(max_attempts))
            else:
                stop_conditions.append(StopAfterAttempt(3))

            if stop_after_delay:
                stop_conditions.append(StopAfterDelay(stop_after_delay))

            wait_strategy = ExponentialBackoff(
                base_delay=base_delay or 0.1,
                max_delay=max_delay or 10.0,
                multiplier=multiplier or 2.0,
                jitter=jitter or 0.1,
            )

            self.policy = RetryPolicy(
                retry_on=retry_conditions,
                stop=stop_conditions,
                wait=wait_strategy,
                reraise=reraise,
            )

    def _execute_sync(self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Execute function with retry logic synchronously.

        Parameters
        ----------
        fn : Callable[P, R]
            Function to execute.
        *args : P.args
            Function arguments.
        **kwargs : P.kwargs
            Function keyword arguments.

        Returns
        -------
        R
            Function result.

        Raises
        ------
        RetryError
            If all retry attempts fail and reraise=False.
        Exception
            Original exception if all retry attempts fail and reraise=True.
        """
        state: RetryState[R, Exception] = RetryState()

        while True:
            state.statistics.attempts += 1

            state_for_hooks = cast(RetryState[object, Exception], state)
            self.policy.execute_before_hooks(state_for_hooks, *args, **kwargs)

            try:
                start_time = time.time()
                result = fn(*args, **kwargs)
                execution_time = time.time() - start_time

                state.statistics.execution_times.append(execution_time)
                state.last_result = result
                state.last_exception = None

                state_for_hooks = cast(RetryState[object, Exception], state)
                self.policy.execute_after_hooks(state_for_hooks, "success", result, None)

                state_for_check = cast(RetryState[object, Exception], state)
                if not any(condition(state_for_check) for condition in self.policy.retry_conditions):
                    state.outcome = RetryOutcome.SUCCESS
                    return result

                self.policy.logger.debug(f"Retrying after attempt {state.attempts} due to result condition")

            except Exception as e:
                state.last_exception = e
                state.last_result = None

                state_for_hooks = cast(RetryState[object, Exception], state)
                self.policy.execute_after_hooks(state_for_hooks, "failure", None, e)

                state_for_check = cast(RetryState[object, Exception], state)
                if not self.policy.should_retry(state_for_check):
                    self.policy.logger.debug(f"Not retrying after exception: {type(e).__name__}: {e}")
                    state.outcome = RetryOutcome.FAILURE
                    if self.policy.reraise:
                        raise
                    raise RetryError(state) from e

                self.policy.logger.debug(f"Retrying after attempt {state.attempts} due to: {type(e).__name__}: {e}")

            state_for_stop = cast(RetryState[object, Exception], state)
            if any(condition(state_for_stop) for condition in self.policy.stop_conditions):
                state.outcome = RetryOutcome.EXHAUSTED
                self.policy.logger.warning(
                    f"Retry exhausted after {state.attempts} attempts ({state.elapsed_time:.2f}s)"
                )

                if state.last_exception:
                    if self.policy.reraise:
                        raise state.last_exception
                    raise RetryError(state) from state.last_exception

                return cast(R, state.last_result)

            delay = self.policy.get_wait_time(state)
            state.statistics.total_delay += delay

            self.policy.logger.debug(f"Waiting {delay:.2f}s before retry attempt {state.attempts + 1}")
            time.sleep(delay)

    async def _execute_async(self, fn: Callable[P, Awaitable[R]], *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Execute function with retry logic asynchronously.

        Parameters
        ----------
        fn : Callable[P, Awaitable[R]]
            Async function to execute.
        *args : P.args
            Function arguments.
        **kwargs : P.kwargs
            Function keyword arguments.

        Returns
        -------
        R
            Function result.

        Raises
        ------
        RetryError
            If all retry attempts fail and reraise=False.
        Exception
            Original exception if all retry attempts fail and reraise=True.
        """
        state: RetryState[R, Exception] = RetryState()

        while True:
            state.statistics.attempts += 1

            state_for_hooks = cast(RetryState[object, Exception], state)
            self.policy.execute_before_hooks(state_for_hooks, *args, **kwargs)

            try:
                start_time = time.time()
                result = await fn(*args, **kwargs)
                execution_time = time.time() - start_time

                state.statistics.execution_times.append(execution_time)
                state.last_result = result
                state.last_exception = None

                state_for_hooks = cast(RetryState[object, Exception], state)
                self.policy.execute_after_hooks(state_for_hooks, "success", result, None)

                state_for_check = cast(RetryState[object, Exception], state)
                if not any(condition(state_for_check) for condition in self.policy.retry_conditions):
                    state.outcome = RetryOutcome.SUCCESS
                    return result

                self.policy.logger.debug(f"Retrying after attempt {state.attempts} due to result condition")

            except Exception as e:
                state.last_exception = e
                state.last_result = None

                state_for_hooks = cast(RetryState[object, Exception], state)
                self.policy.execute_after_hooks(state_for_hooks, "failure", None, e)

                state_for_check = cast(RetryState[object, Exception], state)
                if not self.policy.should_retry(state_for_check):
                    self.policy.logger.debug(f"Not retrying after exception: {type(e).__name__}: {e}")
                    state.outcome = RetryOutcome.FAILURE
                    if self.policy.reraise:
                        raise
                    raise RetryError(state) from e

                self.policy.logger.debug(f"Retrying after attempt {state.attempts} due to: {type(e).__name__}: {e}")

            state_for_stop = cast(RetryState[object, Exception], state)
            if any(condition(state_for_stop) for condition in self.policy.stop_conditions):
                state.outcome = RetryOutcome.EXHAUSTED
                self.policy.logger.warning(
                    f"Retry exhausted after {state.attempts} attempts ({state.elapsed_time:.2f}s)"
                )

                if state.last_exception:
                    if self.policy.reraise:
                        raise state.last_exception
                    raise RetryError(state) from state.last_exception

                return cast(R, state.last_result)

            delay = self.policy.get_wait_time(state)
            state.statistics.total_delay += delay

            self.policy.logger.debug(f"Waiting {delay:.2f}s before retry attempt {state.attempts + 1}")
            await asyncio.sleep(delay)

    @overload
    def __call__(self, fn: Callable[P1, R1]) -> Callable[P1, R1]: ...

    @overload
    def __call__(self, fn: Callable[P2, Awaitable[R2]]) -> Callable[P2, Awaitable[R2]]: ...

    def __call__(self, *args: object, **kwargs: object) -> object:
        """
        Support both decorator and direct call patterns for sync and async functions.

        Parameters
        ----------
        *args : object
            Function if used as decorator, or arguments if used as callable.
        **kwargs : object
            Function keyword arguments if used as callable.

        Returns
        -------
        object
            Decorated function, function result, or awaitable for async operation.

        Raises
        ------
        RuntimeError
            If used incorrectly.
        """
        if len(args) == 1 and callable(args[0]) and not kwargs:
            fn = args[0]

            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*fn_args: object, **fn_kwargs: object) -> object:
                    return await self._execute_async(fn, *fn_args, **fn_kwargs)

                return async_wrapper
            else:

                @functools.wraps(fn)
                def sync_wrapper(*fn_args: object, **fn_kwargs: object) -> object:
                    return self._execute_sync(fn, *fn_args, **fn_kwargs)

                return sync_wrapper

        if hasattr(self, "_fn"):
            assert self._fn is not None, "Context manager function is None"
            return self._execute_sync(self._fn, *args, **kwargs)
        elif hasattr(self, "_async_fn"):
            assert self._async_fn is not None, "Context manager function is None"
            return self._execute_async(self._async_fn, *args, **kwargs)
        else:
            raise RuntimeError("Retry instance must be used as a decorator or within a context manager")

    @contextmanager
    def __call_context(self, fn: Callable[P, R]) -> Generator[Retry[R, E]]:
        """
        Synchronous context manager.

        Parameters
        ----------
        fn : Callable[P, R]
            Function to retry.

        Yields
        ------
        Retry[R, E]
            Self for method chaining.
        """
        self._fn = fn
        try:
            yield self
        finally:
            delattr(self, "_fn")

    @asynccontextmanager
    async def __async_call_context(self, fn: Callable[P, Awaitable[R]]) -> AsyncGenerator[Retry[R, E]]:
        """
        Asynchronous context manager.

        Parameters
        ----------
        fn : Callable[P, Awaitable[R]]
            Async function to retry.

        Yields
        ------
        Retry[R, E]
            Self for method chaining.
        """
        self._async_fn = fn
        try:
            yield self
        finally:
            delattr(self, "_async_fn")

    def calling(self, fn: Callable[P, R]) -> ContextManager[Retry[R, E]]:
        """
        Create a context manager for retrying a synchronous function.

        Parameters
        ----------
        fn : Callable[P, R]
            Function to retry.

        Returns
        -------
        ContextManager[Retry[R, E]]
            Context manager for the function.
        """
        return self.__call_context(fn)

    def async_calling(self, fn: Callable[P, Awaitable[R]]) -> AsyncContextManager[Retry[R, E]]:
        """
        Create a context manager for retrying an asynchronous function.

        Parameters
        ----------
        fn : Callable[P, Awaitable[R]]
            Async function to retry.

        Returns
        -------
        AsyncContextManager[Retry[R, E]]
            Async context manager for the function.
        """
        return self.__async_call_context(fn)


# NOTE: Factory functions for convenient policy creation
def retry(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 10.0,
    multiplier: float = 2.0,
    jitter: float = 0.1,
    retry_on_exceptions: list[type[Exception]] | None = None,
    retry_on_result: Callable[[object], bool] | None = None,
    stop_after_delay: float | None = None,
    reraise: bool = True,
) -> Retry[object, Exception]:
    """
    Create a Retry instance with the specified parameters.

    Parameters
    ----------
    max_attempts : int, optional
        Maximum number of attempts. Default is 3.
    base_delay : float, optional
        Initial delay in seconds. Default is 0.1.
    max_delay : float, optional
        Maximum delay in seconds. Default is 10.0.
    multiplier : float, optional
        Backoff multiplier. Default is 2.0.
    jitter : float, optional
        Random jitter factor. Default is 0.1.
    retry_on_exceptions : list[type[Exception]] or None, optional
        Exception types to retry on.
    retry_on_result : Callable[[object], bool] or None, optional
        Function to determine if result should trigger retry.
    stop_after_delay : float or None, optional
        Maximum total time for retrying in seconds.
    reraise : bool, optional
        Whether to reraise original exception after retries exhausted. Default is True.

    Returns
    -------
    Retry[object, Exception]
        Configured Retry instance.
    """
    return Retry(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        multiplier=multiplier,
        jitter=jitter,
        retry_on_exceptions=retry_on_exceptions,
        retry_on_result=retry_on_result,
        stop_after_delay=stop_after_delay,
        reraise=reraise,
    )
