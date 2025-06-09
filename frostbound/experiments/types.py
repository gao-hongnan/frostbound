from __future__ import annotations

from pathlib import Path
from typing import TypeAlias, TypeVar

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)

DataT = TypeVar("DataT")
MetricValueT = TypeVar("MetricValueT", bound=float | int)

ExperimentID: TypeAlias = str
ArtifactKey: TypeAlias = str
MetricKey: TypeAlias = str
ParameterKey: TypeAlias = str
StorageKey: TypeAlias = str
SerializationFormat: TypeAlias = str

FilePath: TypeAlias = Path | str
ArtifactPath: TypeAlias = str
RelativePath: TypeAlias = str
