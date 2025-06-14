from __future__ import annotations

from typing import Any, Callable, ClassVar, Self, cast

from pydantic import BaseModel

from frostbound.pydanticonf.base import DynamicConfig


class ConfigRegistry:
    _instance: ClassVar[ConfigRegistry | None] = None
    _mappings: dict[str, type[BaseModel]]

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._mappings = {}
        return cls._instance  # type: ignore[return-value]

    def register(self, target: str, config_class: type[BaseModel]) -> None:
        self._mappings[target] = config_class

    def register_decorator(self, target: str) -> Callable[[type[BaseModel]], type[BaseModel]]:
        def decorator(config_class: type[BaseModel]) -> type[BaseModel]:
            self.register(target, config_class)
            return config_class

        return decorator

    def resolve(self, target: str, data: dict[str, Any] | None = None) -> BaseModel:
        if target in self._mappings:
            config_class = self._mappings[target]
            return config_class(**data) if data else config_class()

        # FIXME: Fallback: create a generic DynamicConfig
        generic_class = type("DynamicConfigImpl", (DynamicConfig,), {})
        if data is None:
            data = {}
        data["_target_"] = target
        return cast(BaseModel, generic_class(**data))

    def get_config_class(self, target: str) -> type[BaseModel]:
        if target in self._mappings:
            return self._mappings[target]
        # NOTE: Create a dynamic config class with default target
        return type("DynamicConfigImpl", (DynamicConfig,), {"target_": target})

    def clear(self) -> None:
        self._mappings.clear()


config_registry = ConfigRegistry()
