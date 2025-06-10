from __future__ import annotations

import posixpath
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from frostbound.experiments.constants import ALL_STATUSES, ExperimentStatus, Serializers, StorageBackends
from frostbound.experiments.types import (
    ArtifactKey,
    ArtifactPath,
    ExperimentID,
    ParameterKey,
    StorageKey,
)


class ExperimentMetadataModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: ExperimentID
    created_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    status: str = Field(default=ExperimentStatus.RUNNING)
    tags: list[str] = Field(default_factory=list)
    description: str = Field(default="")
    git_info: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        valid_statuses = ALL_STATUSES
        if value not in valid_statuses:
            raise ValueError(f"Invalid status: {value}. Must be one of {valid_statuses}")
        return value


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    experiment_id: ExperimentID | None = None
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    parameters: dict[ParameterKey, Any] = Field(default_factory=dict)
    storage_backend: str = Field(default=StorageBackends.LOCAL)
    storage_config: dict[str, Any] = Field(default_factory=dict)
    serializer: str = Field(default=Serializers.JSON)
    serializer_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("experiment_id")
    @classmethod
    def generate_id_if_none(cls, value: ExperimentID | None) -> ExperimentID:
        if value is None:
            return f"exp_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        return value


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_key: ArtifactKey
    storage_key: StorageKey
    artifact_type: str
    created_at: float = Field(default_factory=time.time)
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SaveArtifactRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_file: Path
    artifact_path: ArtifactPath | None = None

    @field_validator("source_file")
    @classmethod
    def validate_source_file_exists(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"File not found: {value}")
        if value.is_dir():
            raise ValueError(f"Use save_artifacts() for directories: {value}")
        return value

    @field_validator("artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: ArtifactPath | None) -> ArtifactPath | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Artifact path cannot be empty")
        normalized = posixpath.normpath(value)
        if normalized.startswith(("/", "../")):
            raise ValueError(f"Artifact path must be relative: {value}")
        return normalized


class SaveArtifactsRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_directory: Path
    artifact_path: ArtifactPath | None = None

    @field_validator("source_directory")
    @classmethod
    def validate_source_directory_exists(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"Directory not found: {value}")
        if not value.is_dir():
            raise ValueError(f"Use save_artifact() for files: {value}")
        return value

    @field_validator("artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: ArtifactPath | None) -> ArtifactPath | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Artifact path cannot be empty")
        normalized = posixpath.normpath(value)
        if normalized.startswith(("/", "../")):
            raise ValueError(f"Artifact path must be relative: {value}")
        return normalized


class JsonSerializationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indent: int | None = 4
    ensure_ascii: bool = True
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)


class YamlSerializationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indent: int = 4
    default_flow_style: bool = False
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)


class FileWriteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "w"
    encoding: str = "utf-8"
    newline: str | None = None
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)
