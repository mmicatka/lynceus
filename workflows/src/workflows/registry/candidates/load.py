# workflows/src/workflows/register/candidates/load_candidates.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import (
    ITEM_PARAM,
    SERVICE_ACCOUNT_NAME,
    shard_ids,
)
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates import (
    build_clean_prefix_template,
    build_template_script,
    load_candidates_template,
    merge_shards_template,
    sample_candidates_template,
    shard_candidates_template,
)

SHARD_PREFIX = "shard_id="


def build_load_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    candidates_config = screen_config.candidates
    candidate_prefixes = infra_config.storage.prefixes.candidates
    mount_path = LYNCEUS_VOLUME.mount_path
    num_shards = infra_config.candidates.num_shards

    load_candidates = build_template_script(
        infra_config, "load_candidates", load_candidates_template
    )
    shard_candidates = build_template_script(
        infra_config, "shard_candidates", shard_candidates_template
    )
    merge_shards = build_template_script(
        infra_config, "merge_shards", merge_shards_template
    )

    clean_prefix_template = build_clean_prefix_template()

    with Workflow(
        generate_name=f"{screen_config.name}-candidates-",
        entrypoint="main-dag",
        service_account_name=SERVICE_ACCOUNT_NAME,
    ) as w:
        with DAG(
            name="process-source-dag", inputs=[Parameter(name="source")]
        ) as process_source_dag:
            source_parquet_prefix = (
                f"{candidate_prefixes.raw_parquet}/{{{{inputs.parameters.source}}}}"
            )

            load_task = load_candidates(
                name="load-candidates",
                arguments={
                    "source": "{{inputs.parameters.source}}",
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
                    "output_prefix": f"{candidate_prefixes.shards_staging}",
                    "num_shards": num_shards,
                },
            )

            load_task >> shard_task  # type: ignore

        with DAG(name="main-dag"):
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
                    "output_path": candidate_prefixes.shards,
                },
            )

            cleanup_task = clean_prefix_template(
                name="cleanup-staging",
                arguments={
                    "mount_path": mount_path,
                    "prefix": f"{candidate_prefixes.shards_staging}",
                },
            )

            process_task >> merge_task >> cleanup_task  # type: ignore

            # Moved inside main-dag to attach the sampling tasks appropriately
            if screen_config.candidates.sub_sample:
                subsample_candidates = build_template_script(
                    infra_config, "subsample_candidates", sample_candidates_template
                )

                subsample_candidates = build_template_script(
                    infra_config, "subsample_candidates", sample_candidates_template
                )

                shard_file = f"{SHARD_PREFIX}{ITEM_PARAM}.parquet"
                sample_per_shard = screen_config.candidates.sub_sample // num_shards

                sample_task = subsample_candidates(
                    name="sample-candidates",
                    with_items=shard_ids(num_shards),
                    arguments={
                        "source": shard_file,
                        "mount_path": mount_path,
                        "source_prefix": candidate_prefixes.shards,
                        "parquet_prefix": candidate_prefixes.shards_sample,
                        "num_samples": sample_per_shard,
                    },
                )

                cleanup_task >> sample_task  # type: ignore

    return w
