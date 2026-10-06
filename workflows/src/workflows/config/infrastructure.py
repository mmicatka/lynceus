# workflows/src/workflows/config/infrastructure.py

from typing import Annotated

from pydantic import ByteSize, ConfigDict, PositiveInt, StringConstraints

from workflows.config.base import StrictModel

StoragePrefix = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[^/]+(/[^/]+)*$"),
]


class CandidatePrefixes(StrictModel):
    raw_smiles: StoragePrefix
    raw_parquet: StoragePrefix


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
    initial_shard_size: ByteSize


class TemplateConfig(StrictModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    cpu: str
    memory: str


class InfraConfig(StrictModel):
    storage: StorageConfig
    candidates: CandidatesInfraConfig
    templates: dict[str, TemplateConfig]
