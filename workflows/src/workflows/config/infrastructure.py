# workflows/src/workflows/config/infrastructure.py

from typing import Annotated

from pydantic import ConfigDict, PositiveInt, StringConstraints

from workflows.config.base import StrictModel

StoragePrefix = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[^/]+(/[^/]+)*$"),
]


class CandidatePrefixes(StrictModel):
    raw_smiles: StoragePrefix
    raw_parquet: StoragePrefix
    shards_staging: StoragePrefix
    shards: StoragePrefix


class FilePaths(StrictModel):
    subset_manifest: str


class StoragePrefixes(StrictModel):
    candidates: CandidatePrefixes


class StorageConfig(StrictModel):
    bucket: str
    prefixes: StoragePrefixes
    files: FilePaths


class CandidatesInfraConfig(StrictModel):
    num_shards: PositiveInt


class TemplateConfig(StrictModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    cpu: str
    memory: str


class InfraConfig(StrictModel):
    storage: StorageConfig
    candidates: CandidatesInfraConfig
    templates: dict[str, TemplateConfig]
