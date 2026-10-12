# workflows/src/workflows/config/infrastructure.py

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import PositiveInt, StringConstraints

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
MountPath = Annotated[str, StringConstraints(pattern=r"^/[^/\s]+(/[^/\s]+)*$")]


class TemplateName(StrEnum):
    LOAD_CANDIDATES = "load_candidates"
    SHARD_CANDIDATES = "shard_candidates"
    MERGE_SHARDS = "merge_shards"
    SUBSAMPLE_CANDIDATES = "subsample_candidates"
    GENERATE_CONFORMERS = "generate_conformers"
    GENERATE_FEATURES = "generate_features"
    DOWNLOAD_PDBS = "download_pdbs"
    GENERATE_MANIFEST = "generate_manifest"


class CandidatePrefixes(StrictModel):
    raw_smiles: StoragePrefix
    raw_parquet: StoragePrefix
    shards_staging: StoragePrefix
    shards: StoragePrefix
    shards_sample: StoragePrefix
    conformers: StoragePrefix
    features: StoragePrefix


class TargetPrefixes(StrictModel):
    pdbs: StoragePrefix
    ensembles: StoragePrefix


class StoragePrefixes(StrictModel):
    candidates: CandidatePrefixes
    target: TargetPrefixes


class StorageConfig(StrictModel):
    prefixes: StoragePrefixes


class CandidatesInfraConfig(StrictModel):
    num_shards: PositiveInt


class ResourceQuantities(StrictModel):
    cpu: CpuQuantity
    memory: MemoryQuantity


class ResourceSpec(StrictModel):
    requests: ResourceQuantities
    limits: ResourceQuantities


class VolumeConfig(StrictModel):
    name: str
    claim_name: str
    mount_path: MountPath


class ImageConfig(StrictModel):
    image: str
    image_pull_policy: Literal["Always", "IfNotPresent", "Never"] = "Always"


class TemplateConfig(StrictModel):
    image: ImageConfig
    resources: ResourceSpec


class InfraConfig(StrictModel):
    storage: StorageConfig
    volume: VolumeConfig
    candidates: CandidatesInfraConfig
    templates: dict[TemplateName, TemplateConfig]
