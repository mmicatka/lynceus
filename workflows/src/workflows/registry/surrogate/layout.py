# workflows/src/workflows/registry/surrogate/__init__.py

import os
from dataclasses import dataclass
from typing import Callable, Sequence

from lynceus_core.manifest.common import MANIFEST_SUFFIX

FEATURES_FILENAME = "features.parquet"
DOCKING_RESULTS_FILENAME = "docking_results.parquet"
STAGING_DIRNAME = "staging"
VALIDATION_LABEL = "validation"
SITE_PARAMETERS = ("ensemble", "site_id", "member_id", "center")
SURROGATE_ENSEMBLES_DIRNAME = "ensembles"
MODEL_FILENAME = "model.joblib"
PATH_SEPARATOR = ","


def ref(name: str) -> str:
    return f"{{{{inputs.parameters.{name}}}}}"


@dataclass(frozen=True)
class SiteLayout:
    base_path: str
    surrogate_prefix: str
    target_prefix: str
    screen_name: str

    def _absolute(self, relative: str) -> str:
        return os.path.join(self.base_path, relative)

    @property
    def ensemble_path(self) -> str:
        return self._absolute(os.path.join(self.target_prefix, ref("ensemble")))

    @property
    def surrogate_root(self) -> str:
        return (
            f"{self.surrogate_prefix}/{self.screen_name}/{SURROGATE_ENSEMBLES_DIRNAME}"
        )

    @property
    def site_prefix(self) -> str:
        return f"{self.surrogate_root}/{ref('ensemble')}/{ref('site_id')}"

    def label_prefix(self, label: str) -> str:
        return f"{self.site_prefix}/{label}"

    def label_dir(self, label: str) -> str:
        return self._absolute(self.label_prefix(label))

    def staging_prefix(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{STAGING_DIRNAME}"

    def staging_dir(self, label: str) -> str:
        return self._absolute(self.staging_prefix(label))

    def features_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{FEATURES_FILENAME}"

    def features_path(self, label: str) -> str:
        return self._absolute(self.features_file(label))

    def docking_input_path(self, label: str) -> str:
        return self.features_path(label)

    def docking_results_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{DOCKING_RESULTS_FILENAME}"

    def docking_results_path(self, label: str) -> str:
        return self._absolute(self.docking_results_file(label))

    def labels_path(self, label: str) -> str:
        return self.docking_results_path(label)

    def model_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{MODEL_FILENAME}"

    def model_path(self, label: str) -> str:
        return self._absolute(self.model_file(label))

    def manifest_file(self, label: str) -> str:
        return f"{self.features_file(label)}.{MANIFEST_SUFFIX}"

    def manifest_path(self, label: str) -> str:
        return self._absolute(self.manifest_file(label))

    def _joined(
        self, path_for_label: Callable[[str], str], labels: Sequence[str]
    ) -> str:
        return PATH_SEPARATOR.join(path_for_label(label) for label in labels)

    def features_paths(self, labels: Sequence[str]) -> str:
        return self._joined(self.features_path, labels)

    def labels_paths(self, labels: Sequence[str]) -> str:
        return self._joined(self.labels_path, labels)
