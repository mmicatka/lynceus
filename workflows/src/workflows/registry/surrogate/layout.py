# workflows/src/workflows/registry/surrogate/__init__.py


import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lynceus_core.manifest.common import MANIFEST_SUFFIX

from workflows.config.paths import WorkflowPaths

FEATURES_FILENAME = "features.parquet"
DOCKING_RESULTS_FILENAME = "docking.results.parquet"
STAGING_DIRNAME = "staging"
ROUNDS_DIRNAME = "rounds"
MODELS_DIRNAME = "models"
VALIDATION_LABEL = "validation"
SITE_PARAMETERS = ("ensemble", "site_id", "member_id", "center")
MODEL_FILENAME = "model.joblib"
PATH_SEPARATOR = ","


def ref(name: str) -> str:
    return f"{{{{inputs.parameters.{name}}}}}"


@dataclass(frozen=True)
class SiteLayout:
    paths: WorkflowPaths

    @property
    def base_path(self) -> str:
        return self.paths.mount_path

    def _absolute(self, relative: str) -> str:
        return os.path.join(self.base_path, relative)

    @property
    def ensemble_path(self) -> str:
        return self._absolute(self.paths.target_structures(ref("ensemble")))

    @property
    def site_prefix(self) -> str:
        return str(self.paths.surrogate_screen(ref("ensemble"), ref("site_id")))

    @property
    def validation_site_prefix(self) -> str:
        return str(self.paths.validation_slice(ref("ensemble"), ref("site_id")))

    def label_prefix(self, label: str) -> str:
        if label == VALIDATION_LABEL:
            return self.validation_site_prefix
        return f"{self.site_prefix}/{ROUNDS_DIRNAME}/{label}"

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
        if label == VALIDATION_LABEL:
            raise ValueError("Validation split does not produce a model")
        return f"{self.site_prefix}/{MODELS_DIRNAME}/{label}.{MODEL_FILENAME}"

    def model_path(self, label: str) -> str:
        return self._absolute(self.model_file(label))

    def manifest_file(self, label: str) -> str:
        return f"{self.features_file(label)}.{MANIFEST_SUFFIX}"

    def manifest_path(self, label: str) -> str:
        return self._absolute(self.manifest_file(label))

    def _each(
        self, path_for_label: Callable[[str], str], labels: Sequence[str]
    ) -> tuple[str, ...]:
        return tuple(path_for_label(label) for label in labels)

    def _joined(
        self, path_for_label: Callable[[str], str], labels: Sequence[str]
    ) -> str:
        return PATH_SEPARATOR.join(path_for_label(label) for label in labels)

    def features_paths(self, labels: Sequence[str]) -> str:
        return self._joined(self.features_path, labels)

    def features_path_list(self, labels: Sequence[str]) -> tuple[str, ...]:
        return self._each(self.features_path, labels)

    def labels_paths(self, labels: Sequence[str]) -> str:
        return self._joined(self.labels_path, labels)
