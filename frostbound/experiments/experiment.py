from __future__ import annotations

import contextlib
import json
import os
import posixpath
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator

import yaml
from pydantic import BaseModel

from frostbound.experiments.constants import (
    EMPTY_STRING,
    YAML_EXTENSIONS,
    Categories,
    ExperimentStatus,
    FileExtensions,
    FileNames,
)
from frostbound.experiments.models import ExperimentMetadataModel, SaveArtifactRequest, SaveArtifactsRequest
from frostbound.experiments.types import (
    ArtifactKey,
    ArtifactPath,
    ExperimentID,
    FilePath,
    MetricKey,
    ParameterKey,
    StorageKey,
)

if TYPE_CHECKING:
    from frostbound.experiments.protocols import StorageBackend


def get_git_info() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        dirty = subprocess.call(["git", "diff", "--quiet"]) != 0
        return {
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
        }
    except Exception:
        return {"commit": None, "branch": None, "dirty": None}


class Experiment:
    def __init__(
        self,
        experiment_id: ExperimentID,
        storage: StorageBackend,
    ) -> None:
        self._id = experiment_id
        self._storage = storage

        self._metadata = ExperimentMetadataModel(
            experiment_id=experiment_id,
            git_info=get_git_info(),
        )
        self._artifacts: dict[ArtifactKey, StorageKey] = {}
        self._metrics: dict[MetricKey, float | int] = {}
        self._parameters: dict[ParameterKey, Any] = {}

        self._start_experiment()

    def _start_experiment(self) -> None:
        self._save_metadata()

    @property
    def id(self) -> ExperimentID:
        return self._id

    @property
    def metadata(self) -> ExperimentMetadataModel:
        return self._metadata

    @property
    def artifacts(self) -> dict[ArtifactKey, StorageKey]:
        return self._artifacts.copy()

    @property
    def metrics(self) -> dict[MetricKey, float | int]:
        return self._metrics.copy()

    @property
    def parameters(self) -> dict[ParameterKey, Any]:
        return self._parameters.copy()

    def save_artifact(self, source_file: FilePath, artifact_path: ArtifactPath | None = None) -> ArtifactKey:
        request = SaveArtifactRequest(source_file=Path(source_file), artifact_path=artifact_path)

        filename = request.source_file.name

        if request.artifact_path:
            storage_key = self._generate_storage_key(
                Categories.ARTIFACTS, posixpath.join(request.artifact_path, filename)
            )
        else:
            storage_key = self._generate_storage_key(Categories.ARTIFACTS, filename)

        self._storage.save(storage_key, request.source_file)
        self._artifacts[storage_key] = storage_key
        return storage_key

    def save_artifacts(
        self, source_directory: FilePath, artifact_path: ArtifactPath | None = None
    ) -> list[ArtifactKey]:
        request = SaveArtifactsRequest(source_directory=Path(source_directory), artifact_path=artifact_path)

        artifact_keys: list[ArtifactKey] = []

        for root, _, files in os.walk(request.source_directory):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(request.source_directory)

                if request.artifact_path:
                    dest_path = posixpath.join(request.artifact_path, relative_path.as_posix())
                else:
                    dest_path = relative_path.as_posix()

                storage_key = self._generate_storage_key(Categories.ARTIFACTS, dest_path)
                self._storage.save(storage_key, file_path)
                self._artifacts[storage_key] = storage_key
                artifact_keys.append(storage_key)

        return artifact_keys

    @contextlib.contextmanager
    def _artifact_helper(self, artifact_file: str) -> Generator[str, None, None]:
        norm_path = posixpath.normpath(artifact_file)
        filename = posixpath.basename(norm_path)
        artifact_dir = posixpath.dirname(norm_path)
        artifact_dir = None if artifact_dir == EMPTY_STRING else artifact_dir

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, filename)
            yield tmp_path
            self.save_artifact(tmp_path, artifact_dir)

    def save_dict(self, dictionary: dict[str, Any], artifact_file: str) -> None:
        extension = os.path.splitext(artifact_file)[1]

        with self._artifact_helper(artifact_file) as tmp_path, open(tmp_path, "w") as f:
            if extension in YAML_EXTENSIONS:
                yaml.dump(dictionary, f, indent=2, default_flow_style=False)
            else:
                json.dump(dictionary, f, indent=2, default=str)

    def save_text(self, text: str, artifact_file: str) -> None:
        with self._artifact_helper(artifact_file) as tmp_path, open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)

    def load_artifact(self, key: ArtifactKey, path: FilePath) -> None:
        if key not in self._artifacts:
            raise KeyError(f"Artifact not found: {key}")

        storage_key = self._artifacts[key]
        self._storage.load(storage_key, Path(path))

    def record_metric(self, key: MetricKey, value: float) -> None:
        self._metrics[key] = value
        self._save_to_storage_via_tempfile(
            data=value, category=Categories.METRICS, filename=f"{key}.txt", suffix=FileExtensions.TXT
        )

    def add_parameter(self, key: ParameterKey, value: Any) -> None:
        self._parameters[key] = value

    def complete(self) -> None:
        self._metadata = self._metadata.model_copy(
            update={
                "completed_at": time.time(),
                "status": ExperimentStatus.COMPLETED,
            }
        )
        self._save_metadata()
        self._save_metrics()
        self._save_parameters()

    def _generate_storage_key(self, category: str, key: str) -> StorageKey:
        return f"{self._id}/{category}/{key}"

    def _save_to_storage_via_tempfile(
        self,
        data: BaseModel | dict[str, Any] | float | str,
        category: Categories,
        filename: str,
        suffix: FileExtensions = FileExtensions.JSON,
    ) -> None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=suffix) as tmp_file:
            tmp_path = Path(tmp_file.name)

            if isinstance(data, BaseModel):
                tmp_file.write(data.model_dump_json(indent=4))
            else:
                json.dump(data, tmp_file, indent=4)

        try:
            storage_key = self._generate_storage_key(category, filename)
            self._storage.save(storage_key, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _save_metadata(self) -> None:
        self._save_to_storage_via_tempfile(
            data=self._metadata,
            category=Categories.METADATA,
            filename=FileNames.EXPERIMENT_METADATA,
            suffix=FileExtensions.JSON,
        )

    def _save_parameters(self) -> None:
        self._save_to_storage_via_tempfile(
            data=self._parameters,
            category=Categories.PARAMETERS,
            filename=FileNames.PARAMETERS,
            suffix=FileExtensions.JSON,
        )

    def _save_metrics(self) -> None:
        self._save_to_storage_via_tempfile(
            data=self._metrics,
            category=Categories.METRICS,
            filename=FileNames.METRICS_SUMMARY,
            suffix=FileExtensions.JSON,
        )
