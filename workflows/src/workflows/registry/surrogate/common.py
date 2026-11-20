# workflows/src/workflows/registry/surrogate/common.py


import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hera.workflows import Task

TaskFactory = Callable[..., Task]


def _per_shard(total: int, num_shards: int) -> int:
    return math.ceil(total / num_shards)


@dataclass(frozen=True)
class SampleSpec:
    label: str
    seed: int
    num_random: int
    num_top: int = 0
    model_path: str | None = None
    exclude_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.model_path is None) != (self.num_top == 0):
            raise ValueError(
                f"{self.label}: model_path and a positive num_top must be set together"
            )

    @property
    def task_suffix(self) -> str:
        return self.label.replace("_", "-")

    @property
    def dag_name(self) -> str:
        return f"sample-dag-{self.task_suffix}"

    def plan_arguments(self) -> dict[str, Any]:
        return {} if self.model_path is None else {"model_path": self.model_path}

    def shard_arguments(self, num_shards: int) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "num_random": _per_shard(self.num_random, num_shards),
            "num_top": _per_shard(self.num_top, num_shards),
            "model_path": self.model_path or "",
            "exclude_inputs": list(self.exclude_inputs),
        }


@dataclass(frozen=True)
class SampleTemplates:
    sample: TaskFactory
    merge_shards: TaskFactory
    plan: TaskFactory
    verify_manifest: TaskFactory
    update_manifest: TaskFactory
