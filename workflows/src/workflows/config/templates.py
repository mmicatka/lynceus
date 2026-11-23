# workflows/src/workflows/config/templates.py


from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Self

from hera.workflows import RetryStrategy
from pydantic import Field, model_validator

from workflows.config.common import StrictModel, load_config
from workflows.config.k8s import (
    ImageConfig,
    ResourceSpec,
    ScratchConfig,
    TolerationConfig,
    VolumeConfig,
)

RETRY_STRATEGY = RetryStrategy(limit=3, retry_policy="Always")


class TemplateName(StrEnum):
    PLAN_SHARD_CANDIDATES = "plan_shard_candidates"
    SHARD_CANDIDATES = "shard_candidates"
    MERGE_SHARDS = "merge_shards"
    SUBSAMPLE_CANDIDATES = "subsample_candidates"
    PLAN_PREPROCESS_CANDIDATES = "plan_preprocess_candidates"
    PREPROCESS_CANDIDATE_SHARD = "preprocess_candidate_shard"
    PLAN_FEATURIZE_CANDIDATES = "plan_featurize_candidates"
    FEATURIZE_CANDIDATE_SHARD = "featurize_candidate_shard"
    UPDATE_MANIFEST_LOAD_CANDIDATES = "update_manifest_load_candidates"
    VERIFY_MANIFEST_LOAD_CANDIDATES = "verify_manifest_load_candidates"
    UPDATE_MANIFEST_PREPROCESS_CANDIDATES = "update_manifest_preprocess_candidates"
    VERIFY_MANIFEST_PREPROCESS_CANDIDATES = "verify_manifest_preprocess_candidates"
    UPDATE_MANIFEST_FEATURIZE_CANDIDATES = "update_manifest_featurize_candidates"
    VERIFY_MANIFEST_FEATURIZE_CANDIDATES = "verify_manifest_featurize_candidates"
    VERIFY_SHARD_LAYOUT = "verify_shard_layout"
    DOWNLOAD_PDBS = "download_pdbs"
    GENERATE_PROTEIN_ENSEMBLE_MANIFEST = "generate_protein_ensemble_manifest"
    DETECT_BINDING_SITES = "detect_binding_sites"
    RESOLVE_BINDING_SITES = "resolve_binding_sites"
    RUN_DOCKING = "run_docking"
    PLAN_SURROGATE_SAMPLE = "plan_surrogate_sample"
    SURROGATE_SAMPLE_BY_PREDICTION = "surrogate_sample_by_prediction"
    SURROGATE_TRAIN = "surrogate_train"
    UPDATE_MANIFEST_SURROGATE = "update_manifest_surrogate"
    VERIFY_MANIFEST_SURROGATE = "verify_manifest_surrogate"


class TemplateSpec(StrictModel):
    image: ImageConfig
    resources: ResourceSpec
    scratch: ScratchConfig | None = None
    env: Mapping[str, str] = Field(default_factory=dict)
    node_selector: Mapping[str, str] = Field(default_factory=dict)
    tolerations: tuple[TolerationConfig, ...] = ()
    runtime_class_name: str | None = None
    retry_strategy: RetryStrategy = RETRY_STRATEGY

    @property
    def scratch_path(self) -> str:
        if self.scratch is None:
            raise ValueError("scratch is not configured for this template")
        return self.scratch.mount_path


class TemplatesConfig(StrictModel):
    volume: VolumeConfig
    templates: Mapping[TemplateName, TemplateSpec]

    @model_validator(mode="after")
    def _require_all_templates(self) -> Self:
        missing = sorted(set(TemplateName) - set(self.templates))
        if missing:
            raise ValueError(f"missing templates: {[name.value for name in missing]}")
        return self

    @model_validator(mode="after")
    def _require_scratch_outside_volume(self) -> Self:
        conflicting = sorted(
            name.value
            for name, template in self.templates.items()
            if template.scratch is not None
            and template.scratch.is_within(self.volume.mount_path)
        )
        if conflicting:
            raise ValueError(
                f"scratch mount_path must not equal or sit under volume mount_path "
                f"{self.volume.mount_path!r}, conflicting templates: {conflicting}"
            )
        return self

    def template(self, name: TemplateName) -> TemplateSpec:
        return self.templates[name]


def load_templates_config(path: Path) -> TemplatesConfig:
    return load_config(path, TemplatesConfig)
