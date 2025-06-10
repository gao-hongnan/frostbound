"""
The two _save_metadata() calls will NOT overwrite each other destructively.

  def _start_experiment(self) -> None:
      self._save_metadata()  # Saves initial metadata

  Initial metadata content:
  {
    "experiment_id": "finetuning_20250608_173421",
    "created_at": 1717857261.123,
    "completed_at": null,           // ← Not completed yet
    "status": "running",            // ← Running status
    "tags": ["demo", "finetuning"],
    "description": "Demo finetuning experiment",
    "git_info": {...}
  }


  def complete(self) -> None:
      self._metadata = self._metadata.model_copy(
          update={
              "completed_at": time.time(),    // ← Now has completion time
              "status": "completed",          // ← Updated status
          }
      )
      self._save_metadata()  # Saves UPDATED metadata

  Final metadata content:
  {
    "experiment_id": "finetuning_20250608_173421",
    "created_at": 1717857261.123,    // ← Same (preserved)
    "completed_at": 1717857265.456,  // ← NOW populated
    "status": "completed",           // ← Updated from "running"
    "tags": ["demo", "finetuning"],   // ← Same (preserved)
    "description": "Demo finetuning experiment",
    "git_info": {...}                // ← Same (preserved)
  }


1. Same file path: Both save to {experiment_id}/metadata/experiment.json
2. Intentional overwrite: The second call is meant to update the first
3. Data preservation: model_copy(update={...}) only changes specific fields
4. Atomic operation: Each _save_metadata() writes the complete current state
"""

from __future__ import annotations

import json
import os
import posixpath
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel

from frostbound.experiments.constants import (
    YAML_EXTENSIONS,
    Categories,
    ExperimentStatus,
    FileExtensions,
    FileNames,
)
from frostbound.experiments.models import (
    ExperimentMetadataModel,
    FileWriteOptions,
    JsonSerializationOptions,
    SaveArtifactRequest,
    SaveArtifactsRequest,
    YamlSerializationOptions,
)
from frostbound.experiments.types import (
    ArtifactKey,
    ArtifactPath,
    ExperimentID,
    FilePath,
    MetricKey,
    ParameterKey,
    RelativePath,
    StorageKey,
)
from frostbound.versioning.git_info import get_git_info

if TYPE_CHECKING:
    from frostbound.experiments.protocols import StorageBackend


class Experiment:
    """
    MLflow-inspired experiment tracking system with structured file organization.

    The Experiment class provides two distinct file saving approaches:

    1. **Category-based saving** (structured): Files are organized into predefined categories
       under the experiment directory. This creates a consistent structure:

       ```
       {experiment_id}/
       ├── artifacts/        # User files via save_artifact(), save_dict(), save_text()
       ├── metadata/         # Experiment metadata (automatic)
       ├── metrics/          # Recorded metrics (automatic)
       └── parameters/       # Experiment parameters (automatic)
       ```

    2. **Direct path saving** (flexible): Files can be saved to any relative path
       within the experiment directory using save_file(), bypassing categories.

    Parameters
    ----------
    experiment_id : ExperimentID
        Unique identifier for the experiment (e.g., "llama_0250609_122016")
    storage : StorageBackend
        Storage backend implementation for file operations
    description : str, optional
        Human-readable description of the experiment, by default ""
    tags : list[str] | None, optional
        List of tags for experiment categorization, by default None

    Examples
    --------
    Basic experiment creation and file saving:

    >>> from frostbound.experiments.storage import LocalFileStorage
    >>> storage = LocalFileStorage("/path/to/experiments")
    >>> experiment = Experiment(
    ...     experiment_id="llama_0250609_122016",
    ...     storage=storage,
    ...     description="Llama finetune experiment",
    ...     tags=["finetune", "production"]
    ... )

    The experiment will create this directory structure:

    ```
    /path/to/experiments/llama_0250609_122016/
    └── metadata/
        └── experiment.json  # Created automatically
    ```
    """

    def __init__(
        self,
        experiment_id: ExperimentID,
        storage: StorageBackend,
        description: str = "",
        tags: list[str] | None = None,
    ) -> None:
        self._id = experiment_id
        self._storage = storage

        self._metadata = ExperimentMetadataModel(
            experiment_id=experiment_id,
            description=description,
            tags=tags or [],
            git_info=get_git_info().model_dump(),
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
        """
        Save a single file to the experiment's artifacts directory (category-based).

        This method enforces the structured approach by always saving files under
        the `artifacts/` category within the experiment directory.

        Parameters
        ----------
        source_file : FilePath
            Path to the source file to be saved
        artifact_path : ArtifactPath | None, optional
            Subdirectory path within artifacts/ where the file should be saved.
            If None, saves directly to artifacts/, by default None

        Returns
        -------
        ArtifactKey
            Storage key for the saved artifact (same as storage path)

        Examples
        --------
        Save file to artifacts root:

        >>> experiment.save_artifact("/tmp/model.pkl")
        'llama_0250609_122016/artifacts/model.pkl'

        Save file to artifacts subdirectory:

        >>> experiment.save_artifact("/tmp/config.yaml", artifact_path="configs")
        'llama_0250609_122016/artifacts/configs/config.yaml'

        >>> experiment.save_artifact("/home/user/logs/training.log", artifact_path="logs")
        'llama_0250609_122016/artifacts/logs/training.log'

        Resulting directory structure:

        ```
        llama_0250609_122016/
        └── artifacts/
            ├── model.pkl
            ├── configs/
            │   └── config.yaml
            └── logs/
                └── training.log
        ```

        Notes
        -----
        - The original filename is preserved
        - Intermediate directories are created automatically
        - Files are always saved under artifacts/ category
        - Use save_file() if you need to bypass the artifacts/ prefix
        """
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
        """
        Save an entire directory tree to the experiment's artifacts directory (category-based).

        This method recursively saves all files in a directory while preserving
        the directory structure under the `artifacts/` category.

        Parameters
        ----------
        source_directory : FilePath
            Path to the source directory to be saved recursively
        artifact_path : ArtifactPath | None, optional
            Subdirectory path within artifacts/ where the directory should be saved.
            If None, saves directly to artifacts/, by default None

        Returns
        -------
        list[ArtifactKey]
            List of storage keys for all saved files

        Examples
        --------
        Save directory to artifacts root:

        >>> experiment.save_artifacts("/tmp/model_outputs/")
        ['llama_0250609_122016/artifacts/predictions.csv',
         'llama_0250609_122016/artifacts/metrics.json',
         'llama_0250609_122016/artifacts/plots/accuracy.png']

        Save directory to artifacts subdirectory:

        >>> experiment.save_artifacts("/home/user/training_data/", artifact_path="datasets")
        ['llama_0250609_122016/artifacts/datasets/train.csv',
         'llama_0250609_122016/artifacts/datasets/test.csv',
         'llama_0250609_122016/artifacts/datasets/validation.csv']

        Source directory structure:

        ```
        /tmp/model_outputs/
        ├── predictions.csv
        ├── metrics.json
        └── plots/
            └── accuracy.png
        ```

        Resulting experiment structure:

        ```
        llama_0250609_122016/
        └── artifacts/
            ├── predictions.csv
            ├── metrics.json
            └── plots/
                └── accuracy.png
        ```

        With artifact_path="datasets":

        ```
        llama_0250609_122016/
        └── artifacts/
            └── datasets/
                ├── train.csv
                ├── test.csv
                └── validation.csv
        ```

        Notes
        -----
        - Directory structure is preserved recursively
        - All files are saved under artifacts/ category
        - Empty directories are not created (only files are saved)
        - Large directories may take significant time to process
        """
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

    def save_file(self, source_file: FilePath, relative_path: RelativePath) -> StorageKey:
        """
        Save file to any relative path within experiment directory (direct path saving).

        This method bypasses the category-based structure and allows files to be saved
        directly to any relative path within the experiment directory. This provides
        maximum flexibility for custom directory layouts.

        Parameters
        ----------
        source_file : FilePath
            Path to the source file to be saved
        relative_path : RelativePath
            Relative path within experiment directory where file should be saved.
            Can include subdirectories (e.g., "configs/config.yaml", "logs/debug.log")

        Returns
        -------
        StorageKey
            Storage key for the saved file (experiment_id/relative_path)

        Raises
        ------
        FileNotFoundError
            If the source file does not exist

        Examples
        --------
        Save config file directly to configs/ (bypassing artifacts/):

        >>> experiment.save_file("/tmp/config.yaml", "configs/config.yaml")
        'llama_0250609_122016/configs/config.yaml'

        Save log file to custom logs directory:

        >>> experiment.save_file("/var/log/training.log", "logs/training.log")
        'llama_0250609_122016/logs/training.log'

        Save file to experiment root:

        >>> experiment.save_file("/tmp/README.md", "README.md")
        'llama_0250609_122016/README.md'

        Save file with nested subdirectories:

        >>> experiment.save_file("/tmp/plot.png", "results/visualizations/accuracy_plot.png")
        'llama_0250609_122016/results/visualizations/accuracy_plot.png'

        Resulting directory structure:

        ```
        llama_0250609_122016/
        ├── README.md                          # Root level
        ├── configs/
        │   └── config.yaml                    # Custom config directory
        ├── logs/
        │   └── training.log                   # Custom logs directory
        └── results/
            └── visualizations/
                └── accuracy_plot.png          # Nested custom structure
        ```

        Notes
        -----
        - **No category prefix**: Files are saved directly to the specified path
        - **Flexible structure**: Create any directory layout you need
        - **Automatic directory creation**: Intermediate directories are created automatically
        - **Filename preservation**: Original filename is preserved in the relative_path
        - **Comparison with category-based methods**:

          * save_artifact("file.txt", "configs") → artifacts/configs/file.txt
          * save_file("file.txt", "configs/file.txt") → configs/file.txt

        Use this method when you need files outside the artifacts/ structure or want
        a specific directory layout that doesn't fit the category-based approach.
        """
        source_file_path = Path(source_file)
        if not source_file_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")

        storage_key = f"{self._id}/{relative_path}"
        self._storage.save(storage_key, source_file_path)
        return storage_key

    def save_dict(
        self,
        dictionary: dict[str, Any],
        path: RelativePath,
        json_options: JsonSerializationOptions | None = None,
        yaml_options: YamlSerializationOptions | None = None,
        file_options: FileWriteOptions | None = None,
    ) -> StorageKey:
        """
        Save a dictionary as JSON/YAML file to any path within the experiment directory.

        This method serializes a dictionary to JSON or YAML format based on the file extension
        and saves it to the specified path within the experiment directory. This provides
        full flexibility for organizing files according to your needs.

        Parameters
        ----------
        dictionary : dict[str, Any]
            Dictionary to be serialized and saved
        path : RelativePath
            Relative path within the experiment directory where the file should be saved,
            including filename. Extension determines format: .yaml/.yml → YAML, others → JSON.
        json_options : JsonSerializationOptions | None, optional
            Custom JSON serialization options (indent, ensure_ascii, sort_keys, etc.)
        yaml_options : YamlSerializationOptions | None, optional
            Custom YAML serialization options (indent, default_flow_style, allow_unicode, etc.)
        file_options : FileWriteOptions | None, optional
            Custom file writing options (mode, encoding, newline)

        Returns
        -------
        StorageKey
            Storage key for the saved file (experiment_id/path)

        Examples
        --------
        Save configuration to artifacts directory:

        >>> config = {"model": "gpt-4", "temperature": 0.7}
        >>> experiment.save_dict(config, "artifacts/config.json")
        'llama_0250609_122016/artifacts/config.json'

        Save settings to custom configs directory:

        >>> settings = {"database_url": "localhost", "debug": True}
        >>> experiment.save_dict(settings, "configs/settings.yaml")
        'llama_0250609_122016/configs/settings.yaml'

        Save results to evaluation directory:

        >>> results = {"accuracy": 0.95, "loss": 0.23, "epochs": 100}
        >>> experiment.save_dict(results, "evaluation/metrics.json")
        'llama_0250609_122016/evaluation/metrics.json'

        Save parameters with nested structure:

        >>> hyperparams = {"learning_rate": 0.001, "batch_size": 32}
        >>> experiment.save_dict(hyperparams, "training/hyperparameters.yaml")
        'llama_0250609_122016/training/hyperparameters.yaml'

        Save with custom JSON options (ensure_ascii=False for Unicode support):

        >>> from frostbound.experiments.models import JsonSerializationOptions
        >>> data = {"name": "测试", "emoji": "🚀"}
        >>> json_opts = JsonSerializationOptions(ensure_ascii=False, indent=2)
        >>> experiment.save_dict(data, "artifacts/unicode_data.json", json_options=json_opts)
        'llama_0250609_122016/artifacts/unicode_data.json'

        Resulting directory structure:

        ```
        llama_0250609_122016/
        ├── artifacts/
        │   └── config.json
        ├── configs/
        │   └── settings.yaml
        ├── evaluation/
        │   └── metrics.json
        └── training/
            └── hyperparameters.yaml
        ```

        Notes
        -----
        - **Path flexibility**: Save to any relative path within the experiment directory
        - **Automatic serialization**: Dictionary is converted to JSON/YAML automatically
        - **Format detection**: .yaml/.yml extensions → YAML, others → JSON
        - **Pretty formatting**: JSON uses 2-space indentation, YAML uses default formatting
        - **Directory creation**: Intermediate directories are created automatically
        - **MLflow-style**: This API follows a similar pattern to MLflow's artifact logging
        """
        path = posixpath.normpath(path)
        extension = posixpath.splitext(path)[1]

        json_opts = json_options or JsonSerializationOptions()
        yaml_opts = yaml_options or YamlSerializationOptions()
        file_opts = file_options or FileWriteOptions()

        with tempfile.NamedTemporaryFile(
            mode=file_opts.mode,
            encoding=file_opts.encoding,
            newline=file_opts.newline,
            delete=False,
            **file_opts.extra_kwargs,
        ) as tmp_file:
            if extension in YAML_EXTENSIONS:
                yaml.dump(
                    dictionary,
                    tmp_file,
                    indent=yaml_opts.indent,
                    default_flow_style=yaml_opts.default_flow_style,
                    **yaml_opts.extra_kwargs,
                )
            else:
                json.dump(
                    dictionary,
                    tmp_file,
                    indent=json_opts.indent,
                    ensure_ascii=json_opts.ensure_ascii,
                    **json_opts.extra_kwargs,
                )
            tmp_path = tmp_file.name

        try:
            storage_key = f"{self._id}/{path}"
            self._storage.save(storage_key, Path(tmp_path))
            return storage_key
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def save_text(
        self,
        text: str,
        path: RelativePath,
        file_options: FileWriteOptions | None = None,
    ) -> StorageKey:
        """
        Save text content as a file to any path within the experiment directory.

        This method saves text content directly to a file at the specified path
        within the experiment directory with UTF-8 encoding. This provides full
        flexibility for organizing files according to your needs.

        Parameters
        ----------
        text : str
            Text content to be saved
        path : RelativePath
            Relative path within the experiment directory where the file should be saved,
            including filename.
        file_options : FileWriteOptions | None, optional
            Custom file writing options (mode, encoding, newline)

        Returns
        -------
        StorageKey
            Storage key for the saved file (experiment_id/path)

        Examples
        --------
        Save log content to logs directory:

        >>> log_content = "2024-06-09 12:20:16 - Training started\\n2024-06-09 12:25:30 - Epoch 1 complete"
        >>> experiment.save_text(log_content, "logs/training.log")
        'llama_0250609_122016/logs/training.log'

        Save model summary to artifacts:

        >>> model_summary = "Model: GPT-4\\nParameters: 175B\\nTraining: Supervised"
        >>> experiment.save_text(model_summary, "artifacts/model_summary.txt")
        'llama_0250609_122016/artifacts/model_summary.txt'

        Save README to experiment root:

        >>> readme_text = "# Experiment Overview\\nThis experiment tests..."
        >>> experiment.save_text(readme_text, "README.md")
        'llama_0250609_122016/README.md'

        Save notes to documentation directory:

        >>> notes = "Important findings from today's run..."
        >>> experiment.save_text(notes, "documentation/notes.txt")
        'llama_0250609_122016/documentation/notes.txt'

        Resulting directory structure:

        ```
        llama_0250609_122016/
        ├── README.md
        ├── artifacts/
        │   └── model_summary.txt
        ├── documentation/
        │   └── notes.txt
        └── logs/
            └── training.log
        ```

        Notes
        -----
        - **Path flexibility**: Save to any relative path within the experiment directory
        - **UTF-8 encoding**: All text files are saved with UTF-8 encoding
        - **No automatic formatting**: Text is saved exactly as provided
        - **Directory creation**: Intermediate directories are created automatically
        - **MLflow-style**: This API follows a similar pattern to MLflow's artifact logging
        - Use save_dict() for structured data that needs JSON/YAML formatting
        """
        path = posixpath.normpath(path)
        file_opts = file_options or FileWriteOptions()

        with tempfile.NamedTemporaryFile(
            mode=file_opts.mode,
            encoding=file_opts.encoding,
            newline=file_opts.newline,
            delete=False,
            **file_opts.extra_kwargs,
        ) as tmp_file:
            tmp_file.write(text)
            tmp_path = tmp_file.name

        try:
            storage_key = f"{self._id}/{path}"
            self._storage.save(storage_key, Path(tmp_path))
            return storage_key
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def load_artifact(self, key: ArtifactKey, path: FilePath) -> None:
        if key not in self._artifacts:
            raise KeyError(f"Artifact not found: {key}")

        storage_key = self._artifacts[key]
        self._storage.load(storage_key, Path(path))

    def record_metric(self, key: MetricKey, value: float) -> None:
        """
        Record a metric value and save it to the experiment's metrics directory (category-based).

        This method stores metrics both in memory and persists them as individual files
        under the `metrics/` category for easy access and analysis.

        Parameters
        ----------
        key : MetricKey
            Unique identifier for the metric (e.g., "accuracy", "loss", "f1_score")
        value : float
            Numeric value of the metric

        Examples
        --------
        Record training metrics:

        >>> experiment.record_metric("accuracy", 0.95)
        # Saves to: llama_0250609_122016/metrics/accuracy.txt

        >>> experiment.record_metric("loss", 0.234)
        # Saves to: llama_0250609_122016/metrics/loss.txt

        >>> experiment.record_metric("f1_score", 0.87)
        # Saves to: llama_0250609_122016/metrics/f1_score.txt

        Resulting directory structure:

        ```
        llama_0250609_122016/
        └── metrics/
            ├── accuracy.txt      # Contains: 0.95
            ├── loss.txt          # Contains: 0.234
            └── f1_score.txt      # Contains: 0.87
        ```

        Notes
        -----
        - **Immediate persistence**: Metrics are saved immediately when recorded
        - **Individual files**: Each metric gets its own .txt file for easy parsing
        - **In-memory storage**: Metrics are also stored in memory for quick access
        - **Category-based**: Always saves under metrics/ directory
        - **Automatic filename**: Filename is generated from the metric key
        - Use experiment.metrics property to access all recorded metrics
        """
        self._metrics[key] = value
        self._save_to_storage_via_tempfile(
            data=value, category=Categories.METRICS, filename=f"{key}.txt", suffix=FileExtensions.TXT
        )

    def add_parameter(self, key: ParameterKey, value: Any) -> None:
        """
        Add a parameter to the experiment (stored in memory, persisted on completion).

        Parameters are configuration values, hyperparameters, or other settings that
        characterize the experiment. They are stored in memory and saved to the
        `parameters/` category when the experiment is completed.

        Parameters
        ----------
        key : ParameterKey
            Unique identifier for the parameter (e.g., "learning_rate", "batch_size")
        value : Any
            Value of the parameter (can be any JSON-serializable type)

        Examples
        --------
        Add hyperparameters:

        >>> experiment.add_parameter("learning_rate", 0.001)
        >>> experiment.add_parameter("batch_size", 32)
        >>> experiment.add_parameter("model_name", "gpt-4o-mini")
        >>> experiment.add_parameter("use_dropout", True)

        After calling experiment.complete(), these are saved to:

        ```
        llama_0250609_122016/
        └── parameters/
            └── parameters.json   # Contains all parameters as JSON
        ```

        Notes
        -----
        - **Delayed persistence**: Parameters are only saved when experiment.complete() is called
        - **In-memory storage**: Parameters are stored in memory for immediate access
        - **JSON serialization**: Values must be JSON-serializable
        - **Single file**: All parameters are saved together in parameters.json
        - Use experiment.parameters property to access all stored parameters
        """
        self._parameters[key] = value

    def complete(self) -> None:
        """
        Mark the experiment as completed and persist all data (metadata, metrics, parameters).

        This method finalizes the experiment by updating its status, recording completion
        time, and saving all accumulated data to their respective category directories.

        Examples
        --------
        Complete an experiment:

        >>> experiment.complete()

        This saves the following files:

        ```
        llama_0250609_122016/
        ├── metadata/
        │   └── experiment.json    # Updated with completion time and status
        ├── metrics/
        │   └── metrics.json       # Summary of all recorded metrics
        └── parameters/
            └── parameters.json    # All experiment parameters
        ```

        The metadata.json will be updated from:
        ```json
        {
          "experiment_id": "llama_0250609_122016",
          "status": "running",
          "completed_at": null,
          ...
        }
        ```

        To:
        ```json
        {
          "experiment_id": "llama_0250609_122016",
          "status": "completed",
          "completed_at": 1686307236.789,
          ...
        }
        ```

        Notes
        -----
        - **Idempotent**: Safe to call multiple times
        - **Automatic persistence**: Saves metrics and parameters that haven't been saved yet
        - **Status update**: Changes experiment status from "running" to "completed"
        - **Timestamp recording**: Records exact completion time
        - Call this method in a finally block to ensure experiment is always completed
        """
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
        json_options: JsonSerializationOptions | None = None,
        file_options: FileWriteOptions | None = None,
    ) -> None:
        json_opts = json_options or JsonSerializationOptions()
        file_opts = file_options or FileWriteOptions()

        with tempfile.NamedTemporaryFile(
            mode=file_opts.mode,
            encoding=file_opts.encoding,
            newline=file_opts.newline,
            delete=False,
            suffix=suffix,
            **file_opts.extra_kwargs,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

            if isinstance(data, BaseModel):
                tmp_file.write(data.model_dump_json(indent=json_opts.indent or 4))
            else:
                json.dump(
                    data,
                    tmp_file,
                    indent=json_opts.indent,
                    ensure_ascii=json_opts.ensure_ascii,
                    **json_opts.extra_kwargs,
                )

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
