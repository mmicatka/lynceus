# workflows/src/workflows/config/infrastructure.py


from pydantic import ConfigDict

from workflows.config.base import StrictModel


class StorageConfig(StrictModel):
    bucket: str


class TemplateConfig(StrictModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    cpu: str
    memory: str


class InfraConfig(StrictModel):
    storage: StorageConfig
    templates: dict[str, TemplateConfig]
