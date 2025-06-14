from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings

T = TypeVar("T")
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
    def provide[T](self, dependency_type: type[T]) -> T: ...


class Factory(Protocol[InstanceT_co]):
    def create(self, config: BaseModel, **overrides: Any) -> InstanceT_co: ...
