# libs/lynceus-core/src/lynceus_core/manifest/common.py


import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from lynceus_core.manifest.fingerprint import FINGERPRINT_FIELDS, fingerprint_file
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
    def _describe_file(
        path: Union[str, Path],
        root: Union[str, Path],
        hash_content: bool,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            PATH_FIELD: os.path.relpath(path, root),
            "fingerprint": {**fingerprint_file(path)},
        }
        if hash_content:
            entry[HASH_FIELD] = hash_file(path)
        return entry

    @staticmethod
    def describe_files(
        paths: Iterable[Union[str, Path]],
        root: Union[str, Path],
        hash_content: bool = False,
    ) -> List[Dict[str, Any]]:
        entries = [Manifest._describe_file(path, root, hash_content) for path in paths]
        return sorted(entries, key=lambda entry: entry[PATH_FIELD])

    @staticmethod
    def _fingerprint_view(entry: Dict[str, Any]) -> Dict[str, Any]:
        return {key: entry.get(key) for key in (PATH_FIELD, *FINGERPRINT_FIELDS)}

    @staticmethod
    def _entry_matches(
        entry: Dict[str, Any],
        path: Path,
        deep: bool,
    ) -> bool:
        current = fingerprint_file(path)
        if any(entry.get(field) != current[field] for field in FINGERPRINT_FIELDS):
            return False
        if deep and HASH_FIELD in entry:
            return hash_file(path) == entry[HASH_FIELD]
        return True

    def set_source_files(
        self,
        paths: Iterable[Union[str, Path]],
        root: Union[str, Path],
        key: str = SOURCE_FILES_KEY,
        hash_content: bool = False,
    ) -> "Manifest":
        self.data[key] = self.describe_files(paths, root, hash_content)
        return self

    def set_source_hashes(
        self,
        hashes: Dict[str, str],
        key: str = SOURCE_FILES_KEY,
    ) -> "Manifest":
        entries = self.data.get(key, [])
        known = {entry[PATH_FIELD] for entry in entries}
        unknown = sorted(set(hashes) - known)
        if unknown:
            raise RuntimeError(f"Hashes provided for unknown source files: {unknown}")

        for entry in entries:
            if entry[PATH_FIELD] in hashes:
                entry[HASH_FIELD] = hashes[entry[PATH_FIELD]]
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
        deep: bool = False,
    ) -> List[str]:
        mismatched = []
        for entry in self.data.get(key, []):
            path = Path(root) / entry[PATH_FIELD]
            if not path.is_file() or not self._entry_matches(entry, path, deep):
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
        stored = self.data.get(key)
        if stored is None:
            return False
        current = self.describe_files(Path(root).glob(pattern), root)
        return [self._fingerprint_view(entry) for entry in stored] == current

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
