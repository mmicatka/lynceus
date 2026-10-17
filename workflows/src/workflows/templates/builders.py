# workflows/src/workflows/templates/builders.py

from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from hera.workflows import (
    EmptyDirVolume,
    ExistingVolume,
    Resources,
    RetryStrategy,
    script,
)
from hera.workflows.models import Quantity

from workflows.config.infrastructure import (
    InfraConfig,
    ResourceSpec,
    ScratchConfig,
    TemplateConfig,
    TemplateName,
    VolumeConfig,
)

SCRATCH_VOLUME_NAME = "scratch"
MEMORY_MEDIUM = "Memory"


def _to_hera_quantity(value: str | None) -> Quantity | None:
    return None if value is None else Quantity(root=value)


def _to_hera_resources(spec: ResourceSpec) -> Resources:
    return Resources(
        cpu_request=spec.requests.cpu,
        cpu_limit=spec.limits.cpu,
        memory_request=spec.requests.memory,
        memory_limit=spec.limits.memory,
    )


def _to_hera_scratch_volume(config: ScratchConfig) -> EmptyDirVolume:
    return EmptyDirVolume(
        name=SCRATCH_VOLUME_NAME,
        mount_path=config.mount_path,
        size_limit=_to_hera_quantity(config.size_limit),
        medium=MEMORY_MEDIUM if config.in_memory else None,
    )


def _to_hera_volume(config: VolumeConfig) -> ExistingVolume:
    return ExistingVolume(
        name=config.name,
        claim_name=config.claim_name,
        mount_path=config.mount_path,
    )


def _to_template_name(name: TemplateName) -> str:
    return name.value.replace("_", "-")


@dataclass(frozen=True)
class TemplateFactory:
    volume: VolumeConfig
    templates: dict[TemplateName, TemplateConfig]
    retry_strategy: RetryStrategy | None = None

    @classmethod
    def from_config(
        cls,
        infra_config: InfraConfig,
        retry_strategy: RetryStrategy | None = None,
    ) -> Self:
        return cls(
            volume=infra_config.volume,
            templates=infra_config.templates,
            retry_strategy=retry_strategy,
        )

    def _volumes_for(
        self, template: TemplateConfig
    ) -> list[ExistingVolume | EmptyDirVolume]:
        volumes: list[ExistingVolume | EmptyDirVolume] = [_to_hera_volume(self.volume)]
        if template.scratch:
            volumes.append(_to_hera_scratch_volume(template.scratch))
        return volumes

    def build(self, name: TemplateName, func: Callable) -> Callable:
        template = self.templates[name]
        return script(
            name=_to_template_name(name),
            image=template.image.image,
            image_pull_policy=template.image.image_pull_policy,
            resources=_to_hera_resources(template.resources),
            volumes=self._volumes_for(template),
            retry_strategy=self.retry_strategy,
        )(func)
