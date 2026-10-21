# workflows/src/workflows/registry/surrogate/dags/sample.py

from dataclasses import dataclass
from typing import Any

from hera.workflows import DAG, Parameter, Task

from workflows.config import InfraConfig
from workflows.registry.common import ITEM_PARAM, shard_ids
from workflows.registry.surrogate.layout import SiteLayout

SHARD_FILENAME_PATTERN = "shard_{shard}.parquet"
SAMPLE_PARAMETERS = ("ensemble", "site_id")

MAX_PARALLEL_SOURCES = 3


@dataclass(frozen=True)
class SampleSpec:
    label: str
    num_samples: int
    seed: int

    @property
    def task_suffix(self) -> str:
        return self.label.replace("_", "-")

    @property
    def dag_name(self) -> str:
        return f"surrogate-sample-{self.task_suffix}-dag"


def _shard_filename(shard: str) -> str:
    return SHARD_FILENAME_PATTERN.format(shard=shard)


def _sample_shards_task(
    surrogate_sample: Any,
    infra_config: InfraConfig,
    layout: SiteLayout,
    spec: SampleSpec,
) -> Task:
    candidate_prefixes = infra_config.storage.prefixes.candidates
    num_shards = infra_config.candidates.num_shards

    return surrogate_sample(
        name="sample-shards",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": layout.base_path,
            "source": _shard_filename(ITEM_PARAM),
            "features_input_prefix": candidate_prefixes.features,
            "conformers_input_prefix": candidate_prefixes.conformers,
            "output_prefix": layout.staging_prefix(spec.label),
            "num_samples": spec.num_samples // num_shards,
            "seed": spec.seed,
        },
    )


def _merge_samples_task(
    merge_shards: Any,
    layout: SiteLayout,
    spec: SampleSpec,
) -> Task:
    return merge_shards(
        name="merge-samples",
        arguments={
            "base_path": layout.base_path,
            "input_path": layout.staging_prefix(spec.label),
            "output_path": layout.features_file(spec.label),
        },
    )


def build_sample_dag(
    surrogate_sample: Any,
    merge_shards: Any,
    infra_config: InfraConfig,
    layout: SiteLayout,
    spec: SampleSpec,
) -> DAG:
    with DAG(
        name=spec.dag_name,
        parallelism=MAX_PARALLEL_SOURCES,
        inputs=[Parameter(name=name) for name in SAMPLE_PARAMETERS],
    ) as dag:
        sample_task = _sample_shards_task(surrogate_sample, infra_config, layout, spec)
        merge_task = _merge_samples_task(merge_shards, layout, spec)

        sample_task >> merge_task  # type: ignore

    return dag
