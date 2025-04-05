from __future__ import annotations

from typing import Callable, Generic, TypeVar, overload

S = TypeVar("S")
F = TypeVar("F")
T = TypeVar("T")


class Either(Generic[S, F]):
    """
    A monadic container representing values that can be either a success or a failure.

    This implementation follows functional programming principles to handle operations
    that might fail, without relying on exceptions.

    Parameters
    ----------
    value : S, optional
        The success value to store, by default None
    error : F, optional
        The error value to store, by default None

    Attributes
    ----------
    _value : S or None
        The wrapped success value
    _error : F or None
        The wrapped error value
    _is_success : bool
        Flag indicating if this is a success value

    Notes
    -----
    Either construct should be created using the class methods `success` or
    `failure` rather than directly instantiating.

    Examples
    --------
    >>> def divide(a: int, b: int) -> Either[float, str]:
    ...     if b == 0:
    ...         return Either.failure("Division by zero")
    ...     return Either.success(a / b)
    >>>
    >>> result = divide(10, 2)
    >>> if result.is_success:
    ...     print(f"Result: {result.value}")
    ... else:
    ...     print(f"Error: {result.error}")
    Result: 5.0
    """

    @overload
    def __init__(
        self,
        *,
        value: S,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        error: F,
    ) -> None: ...

    def __init__(
        self,
        *,
        value: S | None = None,
        error: F | None = None,
    ) -> None:
        """
        Initialize an Either instance.

        Either should store exactly one of value or error, not both.

        Parameters
        ----------
        value : S or None, optional
            The success value, by default None
        error : F or None, optional
            The error value, by default None

        Notes
        -----
        It's recommended to use the class methods `success` or `failure`
        instead of direct initialization.
        """
        self._value = value
        self._error = error
        self._is_success = error is None

    @classmethod
    def success(cls, value: S) -> Either[S, F]:
        """
        Create a new Either instance containing a success value.

        Parameters
        ----------
        value : S
            The success value to wrap

        Returns
        -------
        Either[S, F]
            An Either instance containing the success value

        Examples
        --------
        >>> result = Either.success(42)
        >>> result.is_success
        True
        >>> result.value
        42
        """
        return cls(value=value)

    @classmethod
    def failure(cls, error: F) -> Either[S, F]:
        """
        Create a new Either instance containing a failure value.

        Parameters
        ----------
        error : F
            The error value to wrap

        Returns
        -------
        Either[S, F]
            An Either instance containing the error value

        Examples
        --------
        >>> result = Either.failure("error occurred")
        >>> result.is_success
        False
        >>> result.error
        'error occurred'
        """
        return cls(error=error)

    @property
    def is_success(self) -> bool:
        """
        Check if this instance contains a success value.

        Returns
        -------
        bool
            True if this instance contains a success value, False otherwise
        """
        return self._is_success

    @property
    def is_failure(self) -> bool:
        """
        Check if this instance contains a failure value.

        Returns
        -------
        bool
            True if this instance contains a failure value, False otherwise
        """
        return not self._is_success

    @property
    def value(self) -> S:
        """
        Get the success value, raising an error if this is a failure.

        Returns
        -------
        S
            The wrapped success value

        Raises
        ------
        ValueError
            If this is a failure or if the value is None
        """
        if not self._is_success:
            raise ValueError("Cannot access value from a failure Either")

        if self._value is None:
            raise ValueError("Success value is unexpectedly None")

        return self._value

    @property
    def error(self) -> F:
        """
        Get the error value, raising an error if this is a success.

        Returns
        -------
        F
            The wrapped error value

        Raises
        ------
        ValueError
            If this is a success or if the error is None
        """
        if self._is_success:
            raise ValueError("Cannot access error from a success Either")

        if self._error is None:
            raise ValueError("Error value is unexpectedly None")

        return self._error

    def map(self, f: Callable[[S], T]) -> Either[T, F]:
        """
        Apply a function to the success value if this is a success.

        Parameters
        ----------
        f : Callable[[S], T]
            The function to apply to the success value

        Returns
        -------
        Either[T, F]
            A new Either with the result of applying f to the success value,
            or the original error if this is a failure

        Examples
        --------
        >>> result = Either.success(5)
        >>> doubled = result.map(lambda x: x * 2)
        >>> doubled.value
        10
        """
        if self._is_success:
            return Either.success(f(self.value))
        return Either.failure(self.error)

    def flat_map(self, f: Callable[[S], Either[T, F]]) -> Either[T, F]:
        """
        Apply a function that returns an Either to the success value.

        Parameters
        ----------
        f : Callable[[S], Either[T, F]]
            The function to apply to the success value

        Returns
        -------
        Either[T, F]
            The result of applying f to the success value,
            or the original error if this is a failure

        Examples
        --------
        >>> def safe_sqrt(x: float) -> Either[float, str]:
        ...     if x < 0:
        ...         return Either.failure("Cannot take square root of negative number")
        ...     return Either.success(x ** 0.5)
        >>>
        >>> result = Either.success(16)
        >>> sqrt_result = result.flat_map(safe_sqrt)
        >>> sqrt_result.value
        4.0
        """
        if self._is_success:
            return f(self.value)
        return Either.failure(self.error)

    def recover(self, f: Callable[[F], S]) -> Either[S, F]:
        """
        Transform a failure into a success using the provided function.

        Parameters
        ----------
        f : Callable[[F], S]
            The function to apply to the error value

        Returns
        -------
        Either[S, F]
            A new Either with the result of applying f to the error value,
            or the original value if this is already a success

        Examples
        --------
        >>> result = Either.failure("error")
        >>> recovered = result.recover(lambda _: "default value")
        >>> recovered.value
        'default value'
        """
        if not self._is_success:
            return Either.success(f(self.error))
        return self

    def unwrap_or(self, default: S) -> S:
        """
        Get the success value or return the provided default if this is a failure.

        Parameters
        ----------
        default : S
            The default value to return if this is a failure

        Returns
        -------
        S
            The success value or the default

        Examples
        --------
        >>> Either.success(42).unwrap_or(0)
        42
        >>> Either.failure("error").unwrap_or(0)
        0
        """
        if self._is_success and self._value is not None:
            return self._value
        return default

    def unwrap_or_else(self, f: Callable[[F], S]) -> S:
        """
        Get the success value or compute a value from the error if this is a failure.

        Parameters
        ----------
        f : Callable[[F], S]
            The function to apply to the error value

        Returns
        -------
        S
            The success value or the result of applying f to the error

        Examples
        --------
        >>> Either.success(42).unwrap_or_else(lambda e: len(e))
        42
        >>> Either.failure("error").unwrap_or_else(lambda e: len(e))
        5
        """
        if self._is_success and self._value is not None:
            return self._value
        return f(self.error)

    def unwrap(self) -> S:
        """
        Get the success value, raising an error if this is a failure.

        Returns
        -------
        S
            The success value

        Raises
        ------
        ValueError
            If this is a failure

        Examples
        --------
        >>> Either.success(42).unwrap()
        42
        >>> try:
        ...     Either.failure("error").unwrap()
        ... except ValueError as e:
        ...     print(str(e))
        Cannot access value from a failure Either
        """
        return self.value

    def unwrap_error(self) -> F:
        """
        Get the error value, raising an error if this is a success.

        Returns
        -------
        F
            The error value

        Raises
        ------
        ValueError
            If this is a success

        Examples
        --------
        >>> Either.failure("error").unwrap_error()
        'error'
        >>> try:
        ...     Either.success(42).unwrap_error()
        ... except ValueError as e:
        ...     print(str(e))
        Cannot access error from a success Either
        """
        return self.error

    def __repr__(self) -> str:
        """
        Get a string representation of this Either instance.

        Returns
        -------
        str
            A string representation of this Either instance
        """
        if self.is_success:
            return f"Success({self._value!r})"
        return f"Failure({self._error!r})"

    def __str__(self) -> str:
        """
        Get a string representation of this Either instance.

        Returns
        -------
        str
            A string representation of this Either instance
        """
        return self.__repr__()

    def __eq__(self, other: object) -> bool:
        """
        Compare this Either with another object.

        Parameters
        ----------
        other : object
            The object to compare with

        Returns
        -------
        bool
            True if the other object is an Either with the same value or error,
            False otherwise
        """
        if not isinstance(other, Either):
            return False

        if self.is_success != other.is_success:
            return False

        if self.is_success:
            return self._value == other._value
        return self._error == other._error
