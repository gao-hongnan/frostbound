from __future__ import annotations

import importlib
import inspect
from typing import Any, ClassVar, Self, cast

from frostbound.pydanticonf.base import DynamicConfig
from frostbound.pydanticonf.loader import ConfigurationLoader
from frostbound.pydanticonf.types import DependencyProvider, T, TargetClass


class DependencyRegistry:
    _instance: ClassVar[DependencyRegistry | None] = None
    _dependencies: dict[str, Any]

    def __new__(cls: type[Self]) -> Self:
        if cls._instance is None:
            instance = super().__new__(cls)
            cls._instance = instance
            instance._dependencies = {}
        return cast(Self, cls._instance)

    def register(self, name: str, dependency: Any) -> None:
        self._dependencies[name] = dependency

    def register_type(self, dependency_type: type[T], instance: T) -> None:
        self._dependencies[dependency_type.__name__] = instance

    def get(self, name: str) -> Any:
        return self._dependencies.get(name)

    def get_by_type(self, dependency_type: type[T]) -> T | None:
        return cast(T | None, self._dependencies.get(dependency_type.__name__))

    def clear(self) -> None:
        self._dependencies.clear()


class ConfigFactory:
    _registry = DependencyRegistry()

    @classmethod
    def register_dependency(cls: type[Self], name: str, dependency: Any) -> None:
        cls._registry.register(name, dependency)

    @classmethod
    def register_type(cls: type[Self], dependency_type: type[T], instance: T) -> None:
        cls._registry.register_type(dependency_type, instance)

    @classmethod
    def create(cls: type[Self], config: DynamicConfig[T], **overrides: Any) -> T:
        module_path, class_name = config.get_class_path()

        module = importlib.import_module(module_path)
        target_class = cast(TargetClass[T], getattr(module, class_name))

        kwargs = config.extract_config_kwargs()

        cls._inject_dependencies(target_class, kwargs)

        kwargs.update(overrides)

        cls._process_nested_configs(kwargs)

        return target_class(**kwargs)

    @classmethod
    def _inject_dependencies(cls: type[Self], target_class: TargetClass[Any], kwargs: dict[str, Any]) -> None:
        # Get init signature from the target class
        # Since TargetClass is a Protocol with __call__, we inspect the callable itself
        signature = inspect.signature(target_class)

        for param_name, param in signature.parameters.items():
            if param_name == "self" or param_name in kwargs:
                continue

            param_type = param.annotation
            if param_type == inspect.Parameter.empty:
                continue

            dependency = cls._find_dependency(param_name, param_type)
            if dependency is not None:
                kwargs[param_name] = dependency

    @classmethod
    def _find_dependency(cls: type[Self], param_name: str, param_type: Any) -> Any:
        dependency = cls._registry.get(param_name)
        if dependency is not None:
            return dependency

        if hasattr(param_type, "__name__"):
            dependency = cls._registry.get_by_type(param_type)
            if dependency is not None:
                return dependency

        type_name = getattr(param_type, "__name__", str(param_type))
        return cls._registry.get(type_name)

    @classmethod
    def _process_nested_configs(cls: type[Self], kwargs: dict[str, Any]) -> None:
        for key, value in kwargs.items():
            if isinstance(value, DynamicConfig):
                kwargs[key] = cls.create(value)
            elif isinstance(value, dict) and "_target_" in value:
                from frostbound.pydanticonf.loader import ConfigurationLoader

                config = ConfigurationLoader._create_dynamic_config(value)
                if isinstance(config, DynamicConfig):
                    kwargs[key] = cls.create(config)
                else:
                    kwargs[key] = config
            elif isinstance(value, list):
                kwargs[key] = [cls._process_value(item) for item in value]

    @classmethod
    def _process_value(cls: type[Self], value: Any) -> Any:
        if isinstance(value, DynamicConfig):
            return cls.create(value)
        elif isinstance(value, dict) and "_target_" in value:
            config = ConfigurationLoader._create_dynamic_config(value)
            if isinstance(config, DynamicConfig):
                return cls.create(config)
            else:
                return config
        else:
            return value


class FactoryProvider(DependencyProvider):
    def __init__(self, factory: ConfigFactory) -> None:
        self.factory = factory

    def provide(self, dependency_type: type[T]) -> T:
        instance = ConfigFactory._registry.get_by_type(dependency_type)
        if instance is None:
            raise ValueError(f"No dependency registered for type {dependency_type}")
        return instance
