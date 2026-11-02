# libs/lynceus-core/src/lynceus_core/manifest/common.py

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from lynceus_core.manifest.hashing import hash_file

MANIFEST_SUFFIX = "manifest.json"
SOURCE_FILES_KEY = "source_files"
PATH_FIELD = "path"
HASH_FIELD = "blake3"


class Manifest:
    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        filepath: Optional[Union[str, Path]] = None,
    ):
        self.data: Dict[str, Any] = data if data is not None else {}
        self.filepath = Path(filepath) if filepath else None

    @staticmethod
    def describe_files(
        paths: Iterable[Union[str, Path]],
        root: Union[str, Path],
    ) -> List[Dict[str, str]]:
        entries = [
            {
                PATH_FIELD: os.path.relpath(path, root),
                HASH_FIELD: hash_file(path),
            }
            for path in paths
        ]
        return sorted(entries, key=lambda entry: entry[PATH_FIELD])

    def set_source_files(
        self,
        paths: Iterable[Union[str, Path]],
        root: Union[str, Path],
        key: str = SOURCE_FILES_KEY,
    ) -> "Manifest":
        self.data[key] = self.describe_files(paths, root)
        return self

    def resolve_source_files(
        self,
        root: Union[str, Path],
        key: str = SOURCE_FILES_KEY,
    ) -> List[Path]:
        return [Path(root) / entry[PATH_FIELD] for entry in self.data.get(key, [])]

    def verify_source_files(
        self,
        root: Union[str, Path],
        key: str = SOURCE_FILES_KEY,
    ) -> List[str]:
        mismatched = []
        for entry in self.data.get(key, []):
            path = Path(root) / entry[PATH_FIELD]
            if not path.is_file() or hash_file(path) != entry[HASH_FIELD]:
                mismatched.append(entry[PATH_FIELD])
        return mismatched

    def exists(self) -> bool:
        if not self.filepath:
            return False
        return self.filepath.exists() and self.filepath.is_file()

    def load(self) -> "Manifest":
        if not self.filepath:
            raise ValueError("Cannot load: No filepath provided.")
        if not self.exists():
            raise FileNotFoundError(f"Manifest not found at: {self.filepath}")

        with open(self.filepath, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        return self

    def save(self) -> None:
        if not self.filepath:
            raise ValueError("Cannot save: No filepath provided.")

        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def source_files_match(
        self,
        root: Union[str, Path],
        pattern: str,
        key: str = SOURCE_FILES_KEY,
    ) -> bool:
        current = self.describe_files(Path(root).glob(pattern), root)
        return self.data.get(key) == current

    def _is_subset_of(self, other: Union[Dict[str, Any], "Manifest"]) -> bool:
        other_data = other.data if isinstance(other, Manifest) else other
        if not isinstance(other_data, dict):
            return False

        def _is_subset(sub_val: Any, full_val: Any) -> bool:
            if isinstance(sub_val, dict):
                if not isinstance(full_val, dict):
                    return False
                for k, v in sub_val.items():
                    if k not in full_val:
                        return False
                    if not _is_subset(v, full_val[k]):
                        return False
                return True

            elif isinstance(sub_val, list):
                if not isinstance(full_val, list) or len(sub_val) != len(full_val):
                    return False
                for s_item, f_item in zip(sub_val, full_val):
                    if not _is_subset(s_item, f_item):
                        return False
                return True

            else:
                return sub_val == full_val

        return _is_subset(self.data, other_data)

    def exists_superset(self) -> bool:
        if not self.filepath or not self.exists():
            return False

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                file_data = json.load(f)

            return self <= file_data

        except json.JSONDecodeError, OSError:
            return False

    def __le__(self, other: Any) -> bool:
        return self._is_subset_of(other)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return self.data == other
        if isinstance(other, Manifest):
            return self.data == other.data
        return NotImplemented
