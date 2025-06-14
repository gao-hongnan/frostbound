from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from frostbound.pydanticonf.registry import config_registry
from frostbound.pydanticonf.types import SettingsT


class ConfigurationLoader:
    @classmethod
    def load_yaml(cls, yaml_path: Path) -> dict[str, Any]:
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")

        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def load_env_overrides(cls, prefix: str = "") -> dict[str, Any]:
        env_vars: dict[str, Any] = {}
        prefix = f"{prefix}_" if prefix else ""

        for key, value in os.environ.items():
            if key.startswith(prefix):
                cls._set_nested_value(env_vars, key[len(prefix) :], value)

        return env_vars

    @classmethod
    def _set_nested_value(cls, data: dict[str, Any], key: str, value: str) -> None:
        parts = key.lower().split("__")
        current: Any = data

        for part in parts[:-1]:
            dict_key: str | int = int(part) if part.isdigit() else part
            if dict_key not in current:
                current[dict_key] = {}
            current = current[dict_key]

        final_key: str | int = int(parts[-1]) if parts[-1].isdigit() else parts[-1]

        try:
            current[final_key] = json.loads(value)
        except json.JSONDecodeError:
            current[final_key] = value

    @classmethod
    def merge_configs(cls, *configs: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for config in configs:
            cls._deep_merge(result, config)
        return result

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                cls._deep_merge(target[key], value)
            else:
                target[key] = value

    @classmethod
    def load(
        cls,
        settings_class: type[SettingsT],
        yaml_path: Path | None = None,
        env_prefix: str = "",
    ) -> SettingsT:
        yaml_data = {}
        if yaml_path and yaml_path.exists():
            yaml_data = cls.load_yaml(yaml_path)

        env_overrides = cls.load_env_overrides(env_prefix)

        merged_data = cls.merge_configs(yaml_data, env_overrides)

        return settings_class(**merged_data)

    @classmethod
    def process_dynamic_configs(cls, data: dict[str, Any]) -> dict[str, Any]:
        processed: dict[str, Any] = {}

        for key, value in data.items():
            if isinstance(value, dict):
                if "_target_" in value:
                    target_class: type[BaseModel] = cls._resolve_config_class(value["_target_"])
                    processed[key] = target_class(**value)
                else:
                    processed[key] = cls.process_dynamic_configs(value)
            elif isinstance(value, list):
                processed[key] = [
                    (cls._create_dynamic_config(item) if isinstance(item, dict) and "_target_" in item else item)
                    for item in value
                ]
            else:
                processed[key] = value

        return processed

    @classmethod
    def _create_dynamic_config(cls, data: dict[str, Any]) -> BaseModel:
        config_class: type[BaseModel] = cls._resolve_config_class(data["_target_"])
        return config_class(**data)

    @classmethod
    def _resolve_config_class(cls, target: str) -> type[BaseModel]:
        return config_registry.get_config_class(target)
