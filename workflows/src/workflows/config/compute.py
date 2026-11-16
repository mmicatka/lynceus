# workflows/src/workflows/config/compute.py


from typing import Annotated, Literal

from pydantic import PositiveInt, StringConstraints

from workflows.config.common import StrictModel

CpuQuantity = Annotated[str, StringConstraints(pattern=r"^\d+(\.\d+)?m?$")]
MemoryQuantity = Annotated[
    str,
    StringConstraints(pattern=r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?$"),
]
MountPath = Annotated[str, StringConstraints(pattern=r"^/[^/\s]+(/[^/\s]+)*$")]


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


class ScratchConfig(StrictModel):
    mount_path: MountPath = "/scratch"
    size_limit: MemoryQuantity | None = None
    in_memory: bool = False


class ImageConfig(StrictModel):
    image: str
    image_pull_policy: Literal["Always", "IfNotPresent", "Never"] = "Always"
