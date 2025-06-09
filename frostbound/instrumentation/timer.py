from __future__ import annotations

import functools
import inspect
import logging
import timeit
import types
from typing import (
    Any,
    Callable,
    Coroutine,
    Generic,
    ParamSpec,
    Self,
    TypeVar,
    cast,
    overload,
)

P = ParamSpec("P")
R = TypeVar("R", covariant=True)
SyncFunc = TypeVar("SyncFunc", bound=Callable[..., Any])
AsyncFunc = TypeVar("AsyncFunc", bound=Callable[..., Coroutine[Any, Any, Any]])

logger = logging.getLogger(__name__)


def is_coroutine_function(func: Callable[..., Any]) -> bool:
    """Check if a function is a coroutine function."""
    return inspect.iscoroutinefunction(func)


class Timer(Generic[R]):  # NOTE: Timer should be generic over R only
    """A simple timer for measuring execution time.

    Can be used as both a decorator and a context manager, with support
    for both synchronous and asynchronous code.

    Examples
    --------
    >>> # As a decorator
    >>> @timer # Use the functional decorator
    ... def my_function() -> None:
    ...     time.sleep(1)
    ...
    >>> result, exec_time = my_function()
    >>>
    >>> # As a context manager
    >>> def my_sync_ctx_func() -> None:
    ...     with Timer(name="my_sync_ctx_func") as t:
    ...         time.sleep(1)
    ...     print(f"Execution time: {t.execution_time:.4f} seconds")
    ...
    >>> import asyncio
    >>> # Asynchronous context manager
    >>> async def async_function() -> None:
    ...     async with Timer(name="async_function") as t:
    ...         await asyncio.sleep(1)
    ...     print(f"Execution time: {t.execution_time:.4f} seconds")
    """

    def __init__(self, name: str | None = None) -> None:
        """Initialize the timer.

        Parameters
        ----------
        name : str | None, optional
            A name for the timed block or function. Defaults to None.
        """
        self.start_time: float = 0
        self.end_time: float = 0
        self.execution_time: float = 0
        # NOTE: The specific function being timed is stored when __call__ is used
        # or passed during initialization for context manager usage.
        self._timed_func_name: str | None = name

    def __enter__(self) -> Self:
        self.start_time = timeit.default_timer()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        self.end_time = timeit.default_timer()
        self.execution_time = self.end_time - self.start_time
        func_name = self._timed_func_name or "Code block"
        logger.info(f"{func_name} took {self.execution_time:.4f} seconds to execute.")

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)

    @overload
    def __call__(self, func: Callable[P, R]) -> Callable[P, tuple[R, float]]: ...

    @overload
    def __call__(
        self, func: Callable[P, Coroutine[Any, Any, R]]
    ) -> Callable[P, Coroutine[Any, Any, tuple[R, float]]]: ...

    def __call__(
        self, func: Callable[P, R] | Callable[P, Coroutine[Any, Any, R]]
    ) -> Callable[P, tuple[R, float]] | Callable[P, Coroutine[Any, Any, tuple[R, float]]]:
        """Wrap a function to measure its execution time when the Timer *instance* is called.

        Parameters
        ----------
        func : Callable[P, R] | Callable[P, Coroutine[Any, Any, R]]
            The function to wrap.

        Returns
        -------
        Callable: The wrapped function that returns the original result and execution time.
            For sync functions: tuple[R, float]
            For async functions: Coroutine[Any, Any, tuple[R, float]]
        """
        if self._timed_func_name is None:
            self._timed_func_name = func.__name__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> tuple[R, float]:
            start_time = timeit.default_timer()
            sync_func = cast(Callable[P, R], func)
            result = sync_func(*args, **kwargs)
            end_time = timeit.default_timer()
            execution_time = end_time - start_time
            logger.info(f"Function '{self._timed_func_name}' took {execution_time:.4f} seconds to execute.")
            return result, execution_time

        @functools.wraps(func)
        async def awrapper(*args: P.args, **kwargs: P.kwargs) -> tuple[R, float]:
            start_time = timeit.default_timer()
            awaited_func = cast(Callable[P, Coroutine[Any, Any, R]], func)
            result = await awaited_func(*args, **kwargs)
            end_time = timeit.default_timer()
            execution_time = end_time - start_time
            logger.info(f"Function '{self._timed_func_name}' took {execution_time:.4f} seconds to execute.")
            return result, execution_time

        if is_coroutine_function(func):
            return cast(Callable[P, Coroutine[Any, Any, tuple[R, float]]], awrapper)
        return cast(Callable[P, tuple[R, float]], wrapper)


@overload
def timer(func: Callable[P, R]) -> Callable[P, tuple[R, float]]: ...


@overload
def timer(
    func: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, tuple[R, float]]]: ...


@overload
def timer() -> Callable[[Callable[P, R]], Callable[P, tuple[R, float]]]: ...


def timer(
    func: Callable[P, R] | Callable[P, Coroutine[Any, Any, R]] | None = None,
) -> (
    Callable[P, tuple[R, float]]
    | Callable[P, Coroutine[Any, Any, tuple[R, float]]]
    | Callable[[Callable[P, R]], Callable[P, tuple[R, float]]]
):
    """A decorator that times the execution of a function and returns a tuple
    of the original result and the elapsed time.

    Can be used as `@timer` or `@timer()`.

    Parameters
    ----------
    func : Callable, optional
        The function to time.

    Returns
    -------
    Callable
        The wrapped function that includes timing functionality.
        For sync functions, returns tuple[R, float].
        For async functions, returns Coroutine[Any, Any, tuple[R, float]].

    Examples
    --------
    >>> @timer
    ... def my_function() -> int:
    ...     time.sleep(1)
    ...     return 42
    ...
    >>> result, execution_time = my_function()
    >>> print(result)  # 42
    >>> print(f"{execution_time:.2f} seconds")  # ~1.00 seconds
    """
    # If no function is provided, return a partial function
    if func is None:
        # This handles @timer()
        # The lambda ensures we return a callable that has the right signature
        # but just forwards to timer with the given function
        return lambda f: timer(f)

    timer_instance = Timer[R](name=func.__name__)

    if is_coroutine_function(func):
        return cast(Callable[P, Coroutine[Any, Any, tuple[R, float]]], timer_instance(func))

    return cast(Callable[P, tuple[R, float]], timer_instance(func))
