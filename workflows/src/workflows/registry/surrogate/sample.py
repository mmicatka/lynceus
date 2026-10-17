# workflows/src/workflows/registry/surrogate/sample.py

from hera.workflows import DAG, Task

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common import (
    ITEM_PARAM,
    SHARD_FOLDER_PREFIX,
    shard_ids,
)
from workflows.templates import (
    build_clean_prefix_template,
    merge_shards_template,
    surrogate_sample_template,
)
from workflows.templates.builders import TemplateFactory

SURROGATE_SAMPLE_DAG = "surrogate-sample-dag"
SAMPLE_OUTPUT_FILENAME = "docking_input.parquet"
SAMPLE_STAGING_FOLDER = "sample_staging"


def _shard_folder(shard: str) -> str:
    return f"{SHARD_FOLDER_PREFIX}{shard}"


def _round_prefix(model_prefix: str, round_index: int) -> str:
    return f"{model_prefix}/round_{round_index}"


def _sample_shards_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
    staging_prefix: str,
    num_samples: int,
) -> Task:
    features_config = screen_config.filter.features
    num_shards = infra_config.candidates.num_shards
    surrogate_sample = templates.build(
        TemplateName.SURROGATE_SAMPLE, surrogate_sample_template
    )

    return surrogate_sample(
        name="sample-shards",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": _shard_folder(ITEM_PARAM),
            "features_input_prefix": features_config.feature_prefix,
            "conformers_input_prefix": features_config.conformer_prefix,
            "output_prefix": staging_prefix,
            "num_samples": num_samples // num_shards,
        },
    )


def _merge_samples_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    staging_prefix: str,
    output_path: str,
) -> Task:
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)

    return merge_shards(
        name="merge-samples",
        arguments={
            "base_path": infra_config.volume.mount_path,
            "input_path": staging_prefix,
            "output_path": output_path,
        },
    )


def _cleanup_staging_task(infra_config: InfraConfig, staging_prefix: str) -> Task:
    return Task(
        name="cleanup-sample-staging",
        template=build_clean_prefix_template(),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "prefix": staging_prefix,
        },
    )


def build_surrogate_sample_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
    round_index: int = 0,
) -> DAG:
    surrogate_config = screen_config.filter.surrogate
    round_prefix = _round_prefix(surrogate_config.model_prefix, round_index)
    staging_prefix = f"{round_prefix}/{SAMPLE_STAGING_FOLDER}"
    output_path = f"{round_prefix}/{SAMPLE_OUTPUT_FILENAME}"
    num_samples = surrogate_config.rounds[round_index].uniform

    with DAG(name=SURROGATE_SAMPLE_DAG) as dag:
        sample_task = _sample_shards_task(
            templates, infra_config, screen_config, staging_prefix, num_samples
        )
        merge_task = _merge_samples_task(
            templates, infra_config, staging_prefix, output_path
        )
        cleanup_task = _cleanup_staging_task(infra_config, staging_prefix)

        sample_task >> merge_task >> cleanup_task  # type: ignore

    return dag
