from __future__ import annotations

from enum import Enum

DEFAULT_EXPERIMENTS_DIR = "./experiments"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


class Categories(str, Enum):
    METADATA = "metadata"
    PARAMETERS = "parameters"
    METRICS = "metrics"
    ARTIFACTS = "artifacts"

    def __str__(self) -> str:
        return self.value


class FileNames(str, Enum):
    EXPERIMENT_METADATA = "experiment.json"
    PARAMETERS = "parameters.json"
    METRICS_SUMMARY = "summary.json"

    def __str__(self) -> str:
        return self.value


class FileExtensions(str, Enum):
    JSON = ".json"
    TXT = ".txt"
    YAML = ".yaml"
    YML = ".yml"

    def __str__(self) -> str:
        return self.value


class ExperimentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


YAML_EXTENSIONS = frozenset([FileExtensions.YAML, FileExtensions.YML])
ALL_STATUSES = frozenset(
    [ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED, ExperimentStatus.FAILED, ExperimentStatus.CANCELLED]
)
ABSOLUTE_PATH_PREFIXES = ("/", "../")
EMPTY_STRING = ""


class StorageBackends(str, Enum):
    LOCAL = "local"
    MEMORY = "memory"

    def __str__(self) -> str:
        return self.value


class Serializers(str, Enum):
    JSON = "json"
    YAML = "yaml"

    def __str__(self) -> str:
        return self.value
