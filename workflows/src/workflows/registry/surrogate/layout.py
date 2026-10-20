# workflows/src/workflows/registry/surrogate/__init__.py

import os
from dataclasses import dataclass

DOCKING_INPUT_FILENAME = "docking_input.parquet"
DOCKING_RESULTS_FILENAME = "docking.parquet"
STAGING_DIRNAME = "staging"
VALIDATION_LABEL = "validation"
SITE_PARAMETERS = ("ensemble", "site_id", "member_id", "center")


def ref(name: str) -> str:
    return f"{{{{inputs.parameters.{name}}}}}"


@dataclass(frozen=True)
class SiteLayout:
    base_path: str
    surrogate_prefix: str
    target_prefix: str

    @property
    def ensemble_path(self) -> str:
        return os.path.join(self.base_path, self.target_prefix, ref("ensemble"))

    @property
    def site_prefix(self) -> str:
        return f"{self.surrogate_prefix}/{ref('ensemble')}/{ref('site_id')}"

    def label_prefix(self, label: str) -> str:
        return f"{self.site_prefix}/{label}"

    def staging_prefix(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{STAGING_DIRNAME}"

    def docking_input_file(self, label: str) -> str:
        return f"{self.label_prefix(label)}/{DOCKING_INPUT_FILENAME}"

    def docking_input_path(self, label: str) -> str:
        return os.path.join(self.base_path, self.docking_input_file(label))

    def docking_results_path(self, label: str) -> str:
        return os.path.join(
            self.base_path, self.label_prefix(label), DOCKING_RESULTS_FILENAME
        )
