from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from frostbound.experiments.constants import DEFAULT_EXPERIMENTS_DIR, TIMESTAMP_FORMAT
from frostbound.experiments.experiment import Experiment
from frostbound.experiments.models import ExperimentConfig
from frostbound.experiments.storage import LocalFileStorage
from frostbound.experiments.types import ExperimentID, ParameterKey

if TYPE_CHECKING:
    from frostbound.experiments.protocols import StorageBackend


class ExperimentBuilder:
    def __init__(self) -> None:
        self._config = ExperimentConfig()
        self._storage: StorageBackend | None = None
        self._auto_timestamp: bool = False

    def with_id(self, experiment_id: ExperimentID, auto_timestamp: bool = False) -> ExperimentBuilder:
        self._config.experiment_id = experiment_id
        if auto_timestamp:
            self._auto_timestamp = True
        return self

    def with_timestamp(self, enabled: bool = True) -> ExperimentBuilder:
        self._auto_timestamp = enabled
        return self

    def with_description(self, description: str) -> ExperimentBuilder:
        self._config.description = description
        return self

    def with_tags(self, tags: list[str]) -> ExperimentBuilder:
        self._config.tags = tags
        return self

    def add_tag(self, tag: str) -> ExperimentBuilder:
        self._config.tags.append(tag)
        return self

    def with_storage(self, storage: StorageBackend) -> ExperimentBuilder:
        self._storage = storage
        return self

    def add_parameter(self, key: ParameterKey, value: Any) -> ExperimentBuilder:
        self._config.parameters[key] = value
        return self

    def with_parameters(self, parameters: dict[ParameterKey, Any]) -> ExperimentBuilder:
        self._config.parameters.update(parameters)
        return self

    def build(self) -> Experiment:
        if self._storage is None:
            self._storage = LocalFileStorage(Path(DEFAULT_EXPERIMENTS_DIR))

        if self._config.experiment_id is None:
            self._config = self._config.model_copy()

        experiment_id = self._config.experiment_id or "experiment"

        if self._auto_timestamp:
            timestamp = time.strftime(TIMESTAMP_FORMAT)
            experiment_id = f"{experiment_id}_{timestamp}"

        experiment = Experiment(
            experiment_id=experiment_id,
            storage=self._storage,
            description=self._config.description,
            tags=self._config.tags,
        )

        for key, value in self._config.parameters.items():
            experiment.add_parameter(key, value)

        return experiment
