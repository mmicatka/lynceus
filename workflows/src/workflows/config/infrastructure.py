# workflows/src/workflows/config/infrastructure.py


from pydantic import ConfigDict, PositiveInt

from workflows.config.base import StrictModel


class StorageConfig(StrictModel):
    bucket: str


class StageConfig(StrictModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    cpu: str
    memory: str
    max_parallel: PositiveInt


class InfraConfig(StrictModel):
    storage: StorageConfig
    stages: dict[str, StageConfig]
