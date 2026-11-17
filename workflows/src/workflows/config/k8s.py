# workflows/src/workflows/config/k8s.py


from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import PositiveInt, StringConstraints, model_validator

from workflows.config.common import StrictModel

CpuQuantity = Annotated[str, StringConstraints(pattern=r"^\d+(\.\d+)?m?$")]

MemoryQuantity = Annotated[
    str,
    StringConstraints(pattern=r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?$"),
]

MountPath = Annotated[str, StringConstraints(pattern=r"^/[^/\s]+(/[^/\s]+)*$")]

K8sName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=63,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
    ),
]


class ResourceQuantities(StrictModel):
    cpu: CpuQuantity
    memory: MemoryQuantity


class ResourceSpec(StrictModel):
    requests: ResourceQuantities
    limits: ResourceQuantities
    gpu: PositiveInt | None = None


class TolerationConfig(StrictModel):
    key: str
    operator: Literal["Exists", "Equal"] = "Exists"
    value: str | None = None
    effect: Literal["NoSchedule", "PreferNoSchedule", "NoExecute"] = "NoSchedule"

    @model_validator(mode="after")
    def _validate_operator_value(self) -> Self:
        if self.operator == "Equal" and self.value is None:
            raise ValueError("toleration with operator 'Equal' requires a value")
        if self.operator == "Exists" and self.value is not None:
            raise ValueError("toleration with operator 'Exists' must not set a value")
        return self


class ScratchConfig(StrictModel):
    mount_path: MountPath = "/scratch"
    size_limit: MemoryQuantity | None = None
    in_memory: bool = False

    @model_validator(mode="after")
    def _require_size_for_memory_backed(self) -> Self:
        if self.in_memory and self.size_limit is None:
            raise ValueError("in_memory scratch requires a size_limit")
        return self

    def is_within(self, other: MountPath) -> bool:
        return PurePosixPath(self.mount_path).is_relative_to(PurePosixPath(other))


class ImageConfig(StrictModel):
    reference: str
    image_pull_policy: Literal["Always", "IfNotPresent", "Never"] = "Always"


class VolumeConfig(StrictModel):
    name: K8sName
    claim_name: K8sName
    mount_path: MountPath
