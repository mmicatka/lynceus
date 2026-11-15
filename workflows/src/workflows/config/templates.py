# workflows/src/workflows/config/templates.py


from enum import StrEnum

from pydantic import Field

from workflows.config.common import StrictModel
from workflows.config.compute import (
    ImageConfig,
    ResourceSpec,
    ScratchConfig,
    TolerationConfig,
)


class ComputeTemplateName(StrEnum):
    # Candidates
    PLAN_SHARD_CANDIDATES = "plan_shard_candidates"
    SHARD_CANDIDATES = "shard_candidates"
    MERGE_SHARDS = "merge_shards"
    SUBSAMPLE_CANDIDATES = "subsample_candidates"
    PLAN_PREPROCESS_CANDIDATES = "plan_preprocess_candidates"
    GENERATE_CONFORMERS = "generate_conformers"
    GENERATE_FEATURES = "generate_features"
    UPDATE_MANIFEST_LOAD_CANDIDATES = "update_manifest_load_candidates"
    UPDATE_MANIFEST_PREPROCESS_CANDIDATES = "update_manifest_preprocess_candidates"
    VERIFY_MANIFEST_LOAD_CANDIDATES = "verify_manifest_load_candidates"
    VERIFY_MANIFEST_PREPROCESS_CANDIDATES = "verify_manifest_preprocess_candidates"
    VERIFY_SHARD_LAYOUT = "verify_shard_layout"
    # Targets
    DOWNLOAD_PDBS = "download_pdbs"
    GENERATE_PROTEIN_ENSEMBLE_MANIFEST = "generate_protein_ensemble_manifest"
    DETECT_BINDING_SITES = "detect_binding_sites"
    RESOLVE_BINDING_SITES = "resolve_binding_sites"
    # Surrogate
    RUN_DOCKING = "run_docking"
    PLAN_SURROGATE_SAMPLE = "plan_surrogate_sample"
    SURROGATE_SAMPLE = "surrogate_sample"
    SURROGATE_SAMPLE_BY_PREDICTION = "surrogate_sample_by_prediction"
    SURROGATE_TRAIN = "surrogate_train"
    UPDATE_MANIFEST_SURROGATE = "update_manifest_surrogate"
    VERIFY_MANIFEST_SURROGATE = "verify_manifest_surrogate"


class TemplateConfig(StrictModel):
    image: ImageConfig
    resources: ResourceSpec
    scratch: ScratchConfig | None = None
    env: dict[str, str] = Field(default_factory=dict)
    node_selector: dict[str, str] = Field(default_factory=dict)
    tolerations: list[TolerationConfig] = Field(default_factory=list)
    runtime_class_name: str | None = None

    @property
    def scratch_path(self) -> str:
        if self.scratch is None:
            raise ValueError("scratch is not configured for this template")
        return self.scratch.mount_path
