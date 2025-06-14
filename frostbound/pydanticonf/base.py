from __future__ import annotations

from typing import Any, ClassVar, Generic

from pydantic import BaseModel, ConfigDict, Field

from frostbound.pydanticonf.factory import ConfigFactory
from frostbound.pydanticonf.types import InstanceT


class DynamicConfig(BaseModel, Generic[InstanceT]):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_default=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    target_: str = Field(..., alias="_target_", description="Fully qualified class path")

    # NOTE: Subclasses can override this to specify additional fields to exclude
    _exclude_from_kwargs: ClassVar[set[str]] = {"target_"}

    def get_class_path(self) -> tuple[str, str]:
        if not self.target_ or "." not in self.target_:
            raise ValueError(f"Invalid target format: {self.target_}")

        module_path, class_name = self.target_.rsplit(".", 1)
        return module_path, class_name

    def instantiate(self, **dependencies: Any) -> InstanceT:
        return ConfigFactory.create(self, **dependencies)

    def extract_config_kwargs(self) -> dict[str, Any]:
        return self.model_dump(exclude=self._exclude_from_kwargs, by_alias=False, mode="python")
