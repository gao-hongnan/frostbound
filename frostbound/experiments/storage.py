from __future__ import annotations

import shutil
from pathlib import Path

from frostbound.experiments.protocols import StorageBackend
from frostbound.experiments.types import StorageKey


class LocalFileStorage(StorageBackend):
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: StorageKey, path: Path) -> None:
        target_path = self._resolve_path(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target_path)

    def load(self, key: StorageKey, path: Path) -> None:
        source_path = self._resolve_path(key)
        if not source_path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, path)

    def exists(self, key: StorageKey) -> bool:
        return self._resolve_path(key).exists()

    def delete(self, key: StorageKey) -> None:
        file_path = self._resolve_path(key)
        if file_path.exists():
            file_path.unlink()

    def list(self, prefix: StorageKey) -> list[StorageKey]:
        """List all storage keys matching the given prefix.

        Retrieves all stored items whose keys begin with the specified prefix,
        effectively providing a directory-like listing of stored objects. This
        method supports both file and directory prefixes, returning relative
        paths from the base storage directory.

        Parameters
        ----------
        prefix : StorageKey
            The prefix to search for. Can represent either a complete file path
            or a directory path. An empty string returns all stored items.
            Directory prefixes will return all files within that directory and
            its subdirectories.

        Returns
        -------
        list[StorageKey]
            A sorted list of storage keys for all files matching the prefix.
            Keys are returned as relative paths from the base storage directory.
            Returns an empty list if no matching items exist.

        Examples
        --------
        List all items in a specific directory:

        >>> storage = LocalFileStorage('/data/storage')
        >>> storage.list('experiments/2024')
        ['experiments/2024/config.yaml', 'experiments/2024/results.json']

        Check if a specific file exists:

        >>> storage.list('experiments/2024/results.json')
        ['experiments/2024/results.json']  # File exists
        >>> storage.list('experiments/2024/missing.txt')
        []  # File does not exist

        List all stored items:

        >>> storage.list('')
        ['experiments/2024/config.yaml', 'experiments/2024/results.json',
        'models/trained_model.pkl', 'reports/summary.pdf']

        Notes
        -----
        The method performs a recursive search when the prefix represents a
        directory, including all files in subdirectories. Results are always
        sorted lexicographically to ensure consistent ordering across calls.

        The implementation handles three cases:
        1. Non-existent paths return an empty list
        2. File paths return a single-element list if the file exists
        3. Directory paths return all files within the directory tree

        This method only returns paths to files, not directories themselves.
        Empty directories will not appear in the results.
        """
        prefix_path: Path = self._resolve_path(prefix)
        if not prefix_path.exists():
            return []

        if prefix_path.is_file():
            return [prefix]

        keys: list[StorageKey] = []
        for path in prefix_path.rglob("*"):
            if path.is_file():
                relative_path = path.relative_to(self.base_dir)
                keys.append(str(relative_path))

        return sorted(keys)

    def _resolve_path(self, key: StorageKey) -> Path:
        """Resolve a storage key to an absolute filesystem path.

        Converts a relative storage key into an absolute path by combining it with
        the base directory. This method serves as the single source of truth for
        path resolution throughout the storage backend.

        Parameters
        ----------
        key : StorageKey
            A storage key representing a relative path within the storage
            system. Can be a simple filename (e.g., 'data.json') or a
            hierarchical path (e.g., 'experiments/2024/results.json').

        Returns
        -------
        Path
            An absolute filesystem path where the data associated with the
            key should be stored or retrieved from.

        Examples
        --------
        >>> storage = LocalFileStorage('/home/user/storage')
        >>> storage._resolve_path('data.json')
        Path('/home/user/storage/data.json')
        >>> storage._resolve_path('experiments/2024/results.json')
        Path('/home/user/storage/experiments/2024/results.json')
        """
        return self.base_dir / key


class InMemoryStorage(StorageBackend):
    def __init__(self) -> None:
        self._data: dict[StorageKey, bytes] = {}

    def save(self, key: StorageKey, path: Path) -> None:
        self._data[key] = path.read_bytes()

    def load(self, key: StorageKey, path: Path) -> None:
        if key not in self._data:
            raise FileNotFoundError(f"Key not found: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._data[key])

    def exists(self, key: StorageKey) -> bool:
        return key in self._data

    def delete(self, key: StorageKey) -> None:
        self._data.pop(key, None)

    def list(self, prefix: StorageKey) -> list[StorageKey]:
        return sorted([key for key in self._data if key.startswith(prefix)])

    def clear(self) -> None:
        self._data.clear()

    def size(self) -> int:
        return len(self._data)
