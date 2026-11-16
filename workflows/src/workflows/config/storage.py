# workflows/src/workflows/config/storage.py


from typing import Annotated

from pydantic import StringConstraints

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
    conformers: StoragePrefix
    features: StoragePrefix
