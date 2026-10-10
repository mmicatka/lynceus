# workflows/src/workflows/register/candidates/load_candidates.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import ImageName, TemplateName
from workflows.registry.common import (
    ITEM_PARAM,
    SERVICE_ACCOUNT_NAME,
    SHARD_PREFIX,
    SOURCE_PARAM,
    shard_ids,
)
from workflows.resources.retry import IO_RETRY_STRATEGY
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates import (
    build_clean_prefix_template,
    load_candidates_template,
    merge_shards_template,
    sample_candidates_template,
    shard_candidates_template,
)
from workflows.templates.builders import TemplateFactory


def build_load_candidates_workflow(
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Workflow:
    templates = TemplateFactory.from_config(
        infra_config, ImageName.CANDIDATES, retry_strategy=IO_RETRY_STRATEGY
    )

    candidates_config = screen_config.candidates
    candidate_prefixes = infra_config.storage.prefixes.candidates
    mount_path = LYNCEUS_VOLUME.mount_path
    num_shards = infra_config.candidates.num_shards

    load_candidates = templates.build(
        TemplateName.LOAD_CANDIDATES, load_candidates_template
    )
    shard_candidates = templates.build(
        TemplateName.SHARD_CANDIDATES, shard_candidates_template
    )
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)
    clean_prefix = build_clean_prefix_template()

    with Workflow(
        generate_name=f"{screen_config.name}-candidates-",
        entrypoint="main-dag",
        service_account_name=SERVICE_ACCOUNT_NAME,
    ) as w:
        with DAG(
            name="process-source-dag", inputs=[Parameter(name="source")]
        ) as process_source_dag:
            source_parquet_prefix = f"{candidate_prefixes.raw_parquet}/{SOURCE_PARAM}"

            load_task = load_candidates(
                name="load-candidates",
                arguments={
                    "source": SOURCE_PARAM,
                    "mount_path": mount_path,
                    "source_prefix": candidate_prefixes.raw_smiles,
                    "parquet_prefix": source_parquet_prefix,
                },
            )

            shard_task = shard_candidates(
                name="shard-candidates",
                arguments={
                    "mount_path": mount_path,
                    "input_prefix": source_parquet_prefix,
                    "output_prefix": candidate_prefixes.shards_staging,
                    "num_shards": num_shards,
                },
            )

            load_task >> shard_task  # type: ignore

        with DAG(name="main-dag", parallelism=2):
            process_task = process_source_dag(
                name="process-sources",
                with_items=candidates_config.sources,
                arguments={"source": ITEM_PARAM},
            )

            merge_task = merge_shards(
                name="merge-shards",
                with_items=shard_ids(num_shards),
                arguments={
                    "mount_path": mount_path,
                    "input_path": f"{candidate_prefixes.shards_staging}/"
                    f"{SHARD_PREFIX}{ITEM_PARAM}",
                    "output_path": f"{candidate_prefixes.shards}/"
                    f"shard_{ITEM_PARAM}.parquet",
                },
            )

            cleanup_task = clean_prefix(
                name="cleanup-staging",
                arguments={
                    "mount_path": mount_path,
                    "prefix": candidate_prefixes.shards_staging,
                },
            )

            process_task >> merge_task >> cleanup_task  # type: ignore

            if candidates_config.sub_sample:
                subsample_candidates = templates.build(
                    TemplateName.SUBSAMPLE_CANDIDATES, sample_candidates_template
                )

                sample_task = subsample_candidates(
                    name="subsample-candidates",
                    with_items=shard_ids(num_shards),
                    arguments={
                        "source": f"shard_{ITEM_PARAM}.parquet",
                        "mount_path": mount_path,
                        "source_prefix": candidate_prefixes.shards,
                        "parquet_prefix": f"{candidate_prefixes.shards_sample}/"
                        f"shard_{ITEM_PARAM}",
                        "num_samples": candidates_config.sub_sample // num_shards,
                    },
                )

                cleanup_task >> sample_task  # type: ignore

    return w
