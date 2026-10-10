# workflows/src/workflows/config/infrastructure.py

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, StringConstraints

from workflows.config.base import StrictModel

StoragePrefix = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[^/]+(/[^/]+)*$"),
]
CpuQuantity = Annotated[str, StringConstraints(pattern=r"^\d+(\.\d+)?m?$")]
MemoryQuantity = Annotated[
    str,
    StringConstraints(pattern=r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?$"),
]


class TemplateName(StrEnum):
    LOAD_CANDIDATES = "load_candidates"
    SHARD_CANDIDATES = "shard_candidates"
    MERGE_SHARDS = "merge_shards"
    SUBSAMPLE_CANDIDATES = "subsample_candidates"
    GENERATE_CONFORMERS = "generate_conformers"
    GENERATE_FEATURES = "generate_features"


class ImageConfig(StrictModel):
    image: str
    image_pull_policy: Literal["Always", "IfNotPresent", "Never"] = "Always"


class CandidatePrefixes(StrictModel):
    raw_smiles: StoragePrefix
    raw_parquet: StoragePrefix
    shards_staging: StoragePrefix
    shards: StoragePrefix
    shards_sample: StoragePrefix
    conformers: StoragePrefix
    features: StoragePrefix


class StoragePrefixes(StrictModel):
    candidates: CandidatePrefixes


class StorageConfig(StrictModel):
    bucket: str
    prefixes: StoragePrefixes


class CandidatesInfraConfig(StrictModel):
    num_shards: PositiveInt


class ResourceQuantities(StrictModel):
    cpu: CpuQuantity
    memory: MemoryQuantity


class ResourceSpec(StrictModel):
    requests: ResourceQuantities
    limits: ResourceQuantities


class TemplatesConfig(StrictModel):
    default: ResourceSpec
    overrides: dict[TemplateName, ResourceSpec] = Field(default_factory=dict)

    def resources_for(self, name: TemplateName) -> ResourceSpec:
        return self.overrides.get(name, self.default)


class InfraConfig(StrictModel):
    storage: StorageConfig
    volume: VolumeConfig
    images: dict[ImageName, ImageConfig]
    candidates: CandidatesInfraConfig
    templates: TemplatesConfig


class VolumeConfig(StrictModel):
    name: str
    claim_name: str
    mount_path: Annotated[str, StringConstraints(pattern=r"^/[^/\s]+(/[^/\s]+)*$")]


class ImageName(StrEnum):
    CANDIDATES = "candidates"
