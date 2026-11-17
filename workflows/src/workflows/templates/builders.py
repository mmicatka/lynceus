# workflows/src/workflows/templates/builders.py


import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Self

from hera.workflows import (
    EmptyDirVolume,
    Env,
    ExistingVolume,
    Resources,
    RetryStrategy,
    script,
)
from hera.workflows.models import Quantity, Toleration

from workflows.config.k8s import (
    ResourceSpec,
    ScratchConfig,
    TolerationConfig,
    VolumeConfig,
)
from workflows.config.templates import TemplateName, TemplatesConfig, TemplateSpec

RETRY_STRATEGY = RetryStrategy(limit=3, retry_policy="OnFailure")

SCRATCH_VOLUME_NAME = "scratch"
MEMORY_MEDIUM = "Memory"
GPU_RESOURCE_NAME = "nvidia.com/gpu"


def _to_hera_env(env: Mapping[str, str]) -> list[Env] | None:
    return [Env(name=key, value=value) for key, value in env.items()] or None


def _to_hera_tolerations(items: Sequence[TolerationConfig]) -> list[Toleration] | None:
    return [Toleration(**item.model_dump(exclude_none=True)) for item in items] or None


def _to_pod_spec_patch(runtime_class_name: str | None) -> str | None:
    if runtime_class_name is None:
        return None
    return json.dumps({"runtimeClassName": runtime_class_name})


def _to_hera_quantity(value: str | None) -> Quantity | None:
    return None if value is None else Quantity(root=value)


def _to_hera_resources(spec: ResourceSpec) -> Resources:
    return Resources(
        cpu_request=spec.requests.cpu,
        cpu_limit=spec.limits.cpu,
        memory_request=spec.requests.memory,
        memory_limit=spec.limits.memory,
        gpus=spec.gpu,
        gpu_flag=GPU_RESOURCE_NAME,
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
    templates: Mapping[TemplateName, TemplateSpec]
    retry_strategy: RetryStrategy

    @classmethod
    def from_config(
        cls,
        templates_config: TemplatesConfig,
    ) -> Self:
        return cls(
            volume=templates_config.volume,
            templates=templates_config.templates,
            retry_strategy=RETRY_STRATEGY,
        )

    def _volumes_for(
        self, template: TemplateSpec
    ) -> list[ExistingVolume | EmptyDirVolume]:
        volumes: list[ExistingVolume | EmptyDirVolume] = [_to_hera_volume(self.volume)]
        if template.scratch is not None:
            volumes.append(_to_hera_scratch_volume(template.scratch))
        return volumes

    def build(
        self,
        name: TemplateName,
        func: Callable,
        *,
        retry_strategy: RetryStrategy | None = None,
        **kwargs,
    ) -> Callable:
        template = self.templates[name]

        return script(
            name=_to_template_name(name),
            image=template.image.reference,
            image_pull_policy=template.image.image_pull_policy,
            resources=_to_hera_resources(template.resources),
            volumes=self._volumes_for(template),
            retry_strategy=retry_strategy or self.retry_strategy,
            env=_to_hera_env(template.env),
            node_selector=dict(template.node_selector) or None,
            tolerations=_to_hera_tolerations(template.tolerations),
            pod_spec_patch=_to_pod_spec_patch(template.runtime_class_name),
            **kwargs,
        )(func)
