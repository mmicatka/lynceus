# workflows/src/workflows/registry/candidates/load.py

from hera.workflows import DAG, Parameter, Task, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    SHARD_FOLDER_PREFIX,
    SOURCE_PARAM,
    get_template_factory,
    new_workflow,
    shard_ids,
)
from workflows.templates import (
    build_clean_prefix_template,
    load_candidates_template,
    merge_shards_template,
    sample_candidates_template,
    shard_candidates_template,
)
from workflows.templates.builders import TemplateFactory

LOAD_CANDIDATES_DAG = "load-candidates-dag"
PROCESS_SOURCE_DAG = "process-source-dag"
SOURCE_INPUT_NAME = "source"
MAX_PARALLEL_SOURCES = 3


def _shard_filename(shard: str) -> str:
    return f"shard_{shard}.parquet"


def _build_process_source_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
) -> DAG:
    prefixes = infra_config.storage.prefixes.candidates
    base_path = infra_config.volume.mount_path
    source_parquet_prefix = f"{prefixes.raw_parquet}/{SOURCE_PARAM}"

    load_candidates = templates.build(
        TemplateName.LOAD_CANDIDATES, load_candidates_template
    )
    shard_candidates = templates.build(
        TemplateName.SHARD_CANDIDATES, shard_candidates_template
    )

    with DAG(
        name=PROCESS_SOURCE_DAG, inputs=[Parameter(name=SOURCE_INPUT_NAME)]
    ) as dag:
        load_task = load_candidates(
            name="load-candidates",
            arguments={
                "base_path": base_path,
                "source": SOURCE_PARAM,
                "source_prefix": prefixes.raw_smiles,
                "parquet_prefix": source_parquet_prefix,
            },
        )

        shard_task = shard_candidates(
            name="shard-candidates",
            arguments={
                "base_path": base_path,
                "input_prefix": source_parquet_prefix,
                "output_prefix": prefixes.shards_staging,
                "num_shards": infra_config.candidates.num_shards,
                "scratch_path": infra_config.templates[
                    TemplateName.SHARD_CANDIDATES
                ].scratch_path,
                "max_batch_gib": infra_config.candidates.max_batch_gib,
            },
        )
        load_task >> shard_task  # type: ignore

    return dag


def _merge_shards_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)

    return merge_shards(
        name="merge-shards",
        with_items=shard_ids(infra_config.candidates.num_shards),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "input_path": f"{prefixes.shards_staging}/"
            f"{SHARD_FOLDER_PREFIX}{ITEM_PARAM}",
            "output_path": f"{prefixes.shards}/{_shard_filename(ITEM_PARAM)}",
        },
    )


def _cleanup_staging_task(infra_config: InfraConfig) -> Task:
    return Task(
        name="cleanup-staging",
        template=build_clean_prefix_template(),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "prefix": infra_config.storage.prefixes.candidates.shards_staging,
        },
    )


def _subsample_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    sub_sample: int,
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    num_shards = infra_config.candidates.num_shards
    subsample_candidates = templates.build(
        TemplateName.SUBSAMPLE_CANDIDATES, sample_candidates_template
    )

    return subsample_candidates(
        name="subsample-candidates",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": _shard_filename(ITEM_PARAM),
            "source_prefix": prefixes.shards,
            "parquet_prefix": f"{prefixes.shards_sample}/",
            "num_samples": sub_sample // num_shards,
        },
    )


def build_load_candidates_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    candidates_config = screen_config.candidates
    process_source_dag = _build_process_source_dag(templates, infra_config)

    with DAG(name=LOAD_CANDIDATES_DAG, parallelism=MAX_PARALLEL_SOURCES) as dag:
        process_task = Task(
            name="process-sources",
            template=process_source_dag,
            with_items=candidates_config.sources,
            arguments={SOURCE_INPUT_NAME: ITEM_PARAM},
        )
        merge_task = _merge_shards_task(templates, infra_config)
        cleanup_task = _cleanup_staging_task(infra_config)

        process_task >> merge_task >> cleanup_task  # type: ignore

        if candidates_config.sub_sample:
            sample_task = _subsample_task(
                templates, infra_config, candidates_config.sub_sample
            )
            cleanup_task >> sample_task  # type: ignore

    return dag


def build_load_candidates_workflow(
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "candidates") as workflow:
        load_dag = build_load_candidates_dag(templates, infra_config, screen_config)

        with DAG(name=ENTRYPOINT_DAG):
            load_dag(name="load-candidates")

    return workflow
