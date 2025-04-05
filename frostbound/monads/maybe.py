from __future__ import annotations

from typing import Callable, Generic, TypeVar, cast

T = TypeVar("T")
U = TypeVar("U")


class Maybe(Generic[T]):
    """
    A monadic container representing optional values that may or may not exist.

    This implementation follows functional programming principles to handle
    potentially absent values without using None checks throughout the codebase.

    Parameters
    ----------
    value : T or None
        The value to store, or None

    Attributes
    ----------
    _value : T or None
        The wrapped value or None

    Notes
    -----
    Maybe constructs should be created using the class methods `some` or `none`
    rather than directly instantiating.

    Examples
    --------
    >>> def get_config_value(key: str) -> Maybe[str]:
    ...     # Simulating config lookup
    ...     config = {"host": "localhost", "port": "8080"}
    ...     if key in config:
    ...         return Maybe.some(config[key])
    ...     return Maybe.none()
    >>>
    >>> port = get_config_value("port")
    >>> if port.is_some:
    ...     print(f"Port: {port.value}")
    ... else:
    ...     print("Port not configured")
    Port: 8080
    """

    def __init__(self, value: T | None) -> None:
        """
        Initialize a Maybe instance.

        Parameters
        ----------
        value : T or None
            The value to wrap, or None

        Notes
        -----
        It's recommended to use the class methods `some` or `none`
        instead of direct initialization.
        """
        self._value = value

    @classmethod
    def some(cls, value: T) -> Maybe[T]:
        """
        Create a new Maybe instance containing a value.

        Parameters
        ----------
        value : T
            The value to wrap (must not be None)

        Returns
        -------
        Maybe[T]
            A Maybe instance containing the value

        Raises
        ------
        ValueError
            If the provided value is None

        Examples
        --------
        >>> result = Maybe.some(42)
        >>> result.is_some
        True
        >>> result.value
        42
        """
        if value is None:
            raise ValueError("Cannot create Some with a None value")
        return cls(value)

    @classmethod
    def none(cls) -> Maybe[T]:
        """
        Create a new Maybe instance representing no value.

        Returns
        -------
        Maybe[T]
            A Maybe instance with no value

        Examples
        --------
        >>> result = Maybe.none()
        >>> result.is_some
        False
        """
        return cls(None)

    @classmethod
    def from_optional(cls, value: T | None) -> Maybe[T]:
        """
        Create a Maybe from an optional value.

        Parameters
        ----------
        value : T or None
            The value to wrap or None

        Returns
        -------
        Maybe[T]
            A Some if value is not None, otherwise None

        Examples
        --------
        >>> Maybe.from_optional("value").is_some
        True
        >>> Maybe.from_optional(None).is_some
        False
        """
        if value is None:
            return cls.none()
        return cls.some(value)

    @property
    def is_some(self) -> bool:
        """
        Check if this Maybe contains a value.

        Returns
        -------
        bool
            True if this Maybe contains a value, False otherwise

        Examples
        --------
        >>> Maybe.some(42).is_some
        True
        >>> Maybe.none().is_some
        False
        """
        return self._value is not None

    @property
    def is_none(self) -> bool:
        """
        Check if this Maybe contains no value.

        Returns
        -------
        bool
            True if this Maybe contains no value, False otherwise

        Examples
        --------
        >>> Maybe.some(42).is_none
        False
        >>> Maybe.none().is_none
        True
        """
        return self._value is None

    @property
    def value(self) -> T:
        """
        Get the contained value, raising an error if there is none.

        Returns
        -------
        T
            The wrapped value

        Raises
        ------
        ValueError
            If this is a None Maybe

        Examples
        --------
        >>> Maybe.some(42).value
        42
        >>> try:
        ...     Maybe.none().value
        ... except ValueError as e:
        ...     print(str(e))
        Cannot access value from a None Maybe
        """
        if self._value is None:
            raise ValueError("Cannot access value from a None Maybe")
        return self._value

    def map(self, f: Callable[[T], U]) -> Maybe[U]:
        """
        Apply a function to the value if it exists.

        Parameters
        ----------
        f : Callable[[T], U]
            The function to apply to the value

        Returns
        -------
        Maybe[U]
            A new Maybe with the result of applying f to the value,
            or None if this Maybe is None

        Examples
        --------
        >>> Maybe.some(5).map(lambda x: x * 2).value
        10
        >>> Maybe.none().map(lambda x: x * 2).is_none
        True
        """
        if self.is_none:
            return Maybe.none()
        return Maybe.some(f(self.value))

    def flat_map(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """
        Apply a function that returns a Maybe to the value if it exists.

        Parameters
        ----------
        f : Callable[[T], Maybe[U]]
            The function to apply to the value

        Returns
        -------
        Maybe[U]
            The result of applying f to the value,
            or None if this Maybe is None

        Examples
        --------
        >>> def safe_div(x: int, y: int) -> Maybe[float]:
        ...     if y == 0:
        ...         return Maybe.none()
        ...     return Maybe.some(x / y)
        >>>
        >>> Maybe.some(10).flat_map(lambda x: safe_div(x, 2)).value
        5.0
        >>> Maybe.some(10).flat_map(lambda x: safe_div(x, 0)).is_none
        True
        """
        if self.is_none:
            return Maybe.none()
        return f(self.value)

    def filter(self, predicate: Callable[[T], bool]) -> Maybe[T]:
        """
        Filter the value by a predicate.

        Parameters
        ----------
        predicate : Callable[[T], bool]
            The predicate to apply to the value

        Returns
        -------
        Maybe[T]
            This Maybe if it has a value and the predicate returns True,
            otherwise None

        Examples
        --------
        >>> Maybe.some(42).filter(lambda x: x > 10).is_some
        True
        >>> Maybe.some(5).filter(lambda x: x > 10).is_none
        True
        """
        if self.is_none:
            return self

        if predicate(self.value):
            return self

        return Maybe.none()

    def unwrap_or(self, default: T) -> T:
        """
        Get the value or return the provided default.

        Parameters
        ----------
        default : T
            The default value to return if this is None

        Returns
        -------
        T
            The value or the default

        Examples
        --------
        >>> Maybe.some(42).unwrap_or(0)
        42
        >>> Maybe.none().unwrap_or(0)
        0
        """
        if self.is_none:
            return default
        return self.value

    def unwrap_or_else(self, f: Callable[[], T]) -> T:
        """
        Get the value or compute a value with the provided function.

        Parameters
        ----------
        f : Callable[[], T]
            The function to compute a default value

        Returns
        -------
        T
            The value or the result of calling f

        Examples
        --------
        >>> Maybe.some(42).unwrap_or_else(lambda: 0)
        42
        >>> Maybe.none().unwrap_or_else(lambda: 0)
        0
        """
        if self.is_none:
            return f()
        return self.value

    def unwrap(self) -> T:
        """
        Get the value, raising an error if there is none.

        Returns
        -------
        T
            The value

        Raises
        ------
        ValueError
            If this Maybe is None

        Examples
        --------
        >>> Maybe.some(42).unwrap()
        42
        >>> try:
        ...     Maybe.none().unwrap()
        ... except ValueError as e:
        ...     print(str(e))
        Cannot access value from a None Maybe
        """
        return self.value

    def __repr__(self) -> str:
        """
        Get a string representation of this Maybe instance.

        Returns
        -------
        str
            A string representation of this Maybe instance
        """
        if self.is_some:
            return f"Some({self._value!r})"
        return "None"

    def __str__(self) -> str:
        """
        Get a string representation of this Maybe instance.

        Returns
        -------
        str
            A string representation of this Maybe instance
        """
        return self.__repr__()

    def __eq__(self, other: object) -> bool:
        """
        Compare this Maybe with another object.

        Parameters
        ----------
        other : object
            The object to compare with

        Returns
        -------
        bool
            True if the other object is a Maybe with the same value,
            False otherwise
        """
        if not isinstance(other, Maybe):
            return False

        other_maybe = cast(Maybe[T], other)

        if self.is_none and other_maybe.is_none:
            return True

        if self.is_some and other_maybe.is_some:
            return self.value == other_maybe.value

        return False
