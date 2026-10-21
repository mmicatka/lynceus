# workflows/src/workflows/registry/surrogate/__init__.py

import os
from dataclasses import dataclass

FEATURES_FILENAME = "features.parquet"
DOCKING_RESULTS_FILENAME = "docking_results.parquet"
STAGING_DIRNAME = "staging"
VALIDATION_LABEL = "validation"
SITE_PARAMETERS = ("ensemble", "site_id", "member_id", "center")
SURROGATE_ENSEMBLES_DIRNAME = "ensembles"
MODEL_FILENAME = "model.joblib"


def ref(name: str) -> str:
    return f"{{{{inputs.parameters.{name}}}}}"


@dataclass(frozen=True)
class SiteLayout:
    base_path: str
    surrogate_prefix: str
    target_prefix: str
    screen_name: str

    @property
    def ensemble_path(self) -> str:
        return os.path.join(self.base_path, self.target_prefix, ref("ensemble"))

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

    def staging_prefix(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{STAGING_DIRNAME}"

    def features_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{FEATURES_FILENAME}"

    def features_path(self, label: str) -> str:
        return os.path.join(self.base_path, self.features_file(label))

    # This is the same as the features
    def docking_input_path(self, label: str) -> str:
        return self.features_path(label)

    def docking_results_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{DOCKING_RESULTS_FILENAME}"

    def docking_results_path(self, label: str) -> str:
        return os.path.join(self.base_path, self.docking_results_file(label))

    # This is the same as the docking results
    def labels_path(self, label: str) -> str:
        return self.docking_results_path(label)

    def model_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{MODEL_FILENAME}"

    def model_path(self, label: str) -> str:
        return os.path.join(self.base_path, self.model_file(label))
