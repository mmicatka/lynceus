# workflows/src/workflows/config/infrastructure.py

from typing import Annotated

from pydantic import PositiveInt, StringConstraints

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
    shards_sample: StoragePrefix


class StoragePrefixes(StrictModel):
    candidates: CandidatePrefixes


class StorageConfig(StrictModel):
    bucket: str
    prefixes: StoragePrefixes


class CandidatesInfraConfig(StrictModel):
    num_shards: PositiveInt


class ResourcesConfig(StrictModel):
    cpu: str
    memory: str


class TemplateConfig(StrictModel):
    requests: ResourcesConfig
    limits: ResourcesConfig


class InfraConfig(StrictModel):
    storage: StorageConfig
    candidates: CandidatesInfraConfig
    templates: dict[str, TemplateConfig]
