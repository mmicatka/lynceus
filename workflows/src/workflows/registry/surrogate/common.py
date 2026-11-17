# workflows/src/workflows/registry/surrogate/common.py


from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SampleSpec(ABC):
    label: str
    seed: int

    @property
    def task_suffix(self) -> str:
        return self.label.replace("_", "-")

    @property
    def dag_name(self) -> str:
        return f"surrogate-sample-{self.task_suffix}-dag"

    def plan_arguments(self) -> dict[str, Any]:
        return {}

    @abstractmethod
    def shard_arguments(self, num_shards: int) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RandomSampleSpec(SampleSpec):
    num_samples: int

    def shard_arguments(self, num_shards: int) -> dict[str, Any]:
        return {
            "num_samples": self.num_samples // num_shards,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class PredictionSampleSpec(SampleSpec):
    model_path: str
    num_top: int
    num_random: int
    exclude_inputs: tuple[str, ...] = ()

    def plan_arguments(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "exclude_inputs": list(self.exclude_inputs),
        }

    def shard_arguments(self, num_shards: int) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "num_top": self.num_top // num_shards,
            "num_random": self.num_random // num_shards,
            "seed": self.seed,
            "exclude_inputs": list(self.exclude_inputs),
        }


@dataclass(frozen=True)
class SampleTemplates:
    sample: dict[type[SampleSpec], Any]
    merge_shards: Any
    plan: Any
    verify_manifest: Any
    update_manifest: Any

    def sample_for(self, spec: SampleSpec) -> Any:
        return self.sample[type(spec)]
