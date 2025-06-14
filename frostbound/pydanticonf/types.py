from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel
from pydantic_settings import BaseSettings

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)

SettingsT = TypeVar("SettingsT", bound=BaseSettings)

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ConfigT_co = TypeVar("ConfigT_co", bound=BaseModel, covariant=True)

InstanceT = TypeVar("InstanceT")
InstanceT_co = TypeVar("InstanceT_co", covariant=True)

DependencyT = TypeVar("DependencyT")

TargetT = TypeVar("TargetT", bound=str)


class Instantiable(Protocol[InstanceT_co]):
    def instantiate(self, **dependencies: Any) -> InstanceT_co: ...


class ConfigProvider(Protocol[ConfigT_co]):
    def get_config(self) -> ConfigT_co: ...


class DependencyProvider(Protocol):
    def provide(self, dependency_type: type[T]) -> T: ...


class Factory(Protocol[InstanceT_co]):
    def create(self, config: BaseModel, **overrides: Any) -> InstanceT_co: ...


@runtime_checkable
class ClassWithInit(Protocol[T_co]):
    """Protocol for classes with __init__ method that can be instantiated."""

    def __init__(self, **kwargs: Any) -> None: ...


class TargetClass(Protocol[T_co]):
    """Protocol for target classes that can be instantiated with kwargs."""

    __name__: str
    __module__: str

    def __call__(self, **kwargs: Any) -> T_co: ...
