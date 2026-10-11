# workflows/src/workflows/templates/builders.py

from dataclasses import dataclass
from typing import Callable

from hera.workflows import ExistingVolume, Resources, RetryStrategy, script

from workflows.config.infrastructure import (
    ImageConfig,
    ImageName,
    InfraConfig,
    ResourceSpec,
    TemplateName,
    TemplatesConfig,
    VolumeConfig,
)


def _to_hera_resources(spec: ResourceSpec) -> Resources:
    return Resources(
        cpu_request=spec.requests.cpu,
        cpu_limit=spec.limits.cpu,
        memory_request=spec.requests.memory,
        memory_limit=spec.limits.memory,
    )


def _to_hera_volume(config: VolumeConfig) -> ExistingVolume:
    return ExistingVolume(
        name=config.name,
        claim_name=config.claim_name,
        mount_path=config.mount_path,
    )


@dataclass(frozen=True)
class TemplateFactory:
    image: ImageConfig
    volume: VolumeConfig
    templates: TemplatesConfig
    retry_strategy: RetryStrategy | None = None

    @classmethod
    def from_config(
        cls,
        infra_config: InfraConfig,
        image_name: ImageName,
        retry_strategy: RetryStrategy | None = None,
    ) -> "TemplateFactory":
        if image_name not in infra_config.images:
            raise RuntimeError(f"No image configured for '{image_name.value}'")
        return cls(
            image=infra_config.images[image_name],
            volume=infra_config.volume,
            templates=infra_config.templates,
            retry_strategy=retry_strategy,
        )

    def build(self, name: TemplateName, func: Callable) -> Callable:
        return script(
            name=name.value.replace("_", "-"),
            image=self.image.image,
            image_pull_policy=self.image.image_pull_policy,
            resources=_to_hera_resources(self.templates.resources_for(name)),
            volumes=[_to_hera_volume(self.volume)],
            retry_strategy=self.retry_strategy,
        )(func)
