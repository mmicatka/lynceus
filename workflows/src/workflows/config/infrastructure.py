# workflows/src/workflows/config/infrastructure.py


from typing import Annotated

from pydantic import PositiveInt, StringConstraints

from workflows.config.common import StrictModel

StoragePrefix = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[^/]+(/[^/]+)*$"),
]


class CandidatePrefixes(StrictModel):
    raw_smiles: StoragePrefix
    raw_parquet: StoragePrefix
    shards_staging: StoragePrefix
    shards: StoragePrefix
    shards_manifests: str
    shards_sample: StoragePrefix
    conformers: StoragePrefix
    features: StoragePrefix


class TargetPrefixes(StrictModel):
    pdbs: StoragePrefix
    ensembles: StoragePrefix


class SurrogatePrefixes(StrictModel):
    root: StoragePrefix


class StoragePrefixes(StrictModel):
    candidates: CandidatePrefixes
    target: TargetPrefixes
    surrogate: SurrogatePrefixes


class StorageConfig(StrictModel):
    prefixes: StoragePrefixes


class CandidatesInfraConfig(StrictModel):
    num_shards: PositiveInt
    max_batch_gib: PositiveInt


class InfraConfig(StrictModel):
    storage: StorageConfig
    volume: VolumeConfig
    candidates: CandidatesInfraConfig
    templates: dict[ComputeTemplateName, TemplateConfig]
