# workflows/src/workflows/registry/surrogate/dags/sample.py

from hera.workflows import DAG, Task

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common import ITEM_PARAM, shard_ids
from workflows.templates import (
    merge_shards_template,
    surrogate_sample_template,
)
from workflows.templates.builders import TemplateFactory

SURROGATE_SAMPLE_DAG = "surrogate-sample-dag"
SHARD_FILENAME_PATTERN = "shard_{shard}.parquet"

MAX_PARALLEL_SOURCES = 3

PARQUET_SUFFIX = ".parquet"


def _round_file(prefix: str, round_index: int) -> str:
    return f"{_round_path(prefix, round_index)}{PARQUET_SUFFIX}"


def _round_name(round_index: int) -> str:
    return f"round_{round_index}"


def _round_path(prefix: str, round_index: int) -> str:
    return f"{prefix}/{_round_name(round_index)}"


def _shard_filename(shard: str) -> str:
    return SHARD_FILENAME_PATTERN.format(shard=shard)


def _sample_shards_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    staging_path: str,
    num_samples: int,
) -> Task:
    candidate_prefixes = infra_config.storage.prefixes.candidates
    num_shards = infra_config.candidates.num_shards

    surrogate_sample = templates.build(
        TemplateName.SURROGATE_SAMPLE, surrogate_sample_template
    )

    return surrogate_sample(
        name="sample-shards",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": _shard_filename(ITEM_PARAM),
            "features_input_prefix": candidate_prefixes.features,
            "conformers_input_prefix": candidate_prefixes.conformers,
            "output_prefix": staging_path,
            "num_samples": num_samples // num_shards,
        },
    )


def _merge_samples_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    staging_path: str,
    output_path: str,
) -> Task:
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)

    return merge_shards(
        name="merge-samples",
        arguments={
            "base_path": infra_config.volume.mount_path,
            "input_path": staging_path,
            "output_path": output_path,
        },
    )


def build_surrogate_sample_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
    round_index: int = 0,
) -> DAG:
    surrogate_prefixes = infra_config.storage.prefixes.surrogate
    staging_path = _round_path(surrogate_prefixes.samples_staging, round_index)
    output_path = _round_file(surrogate_prefixes.samples, round_index)
    num_samples = screen_config.filter.surrogate.rounds[round_index].uniform

    with DAG(name=SURROGATE_SAMPLE_DAG, parallelism=MAX_PARALLEL_SOURCES) as dag:
        sample_task = _sample_shards_task(
            templates, infra_config, staging_path, num_samples
        )
        merge_task = _merge_samples_task(
            templates, infra_config, staging_path, output_path
        )

        sample_task >> merge_task  # type: ignore

    return dag
