# workflows/src/workflows/registry/candidates.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.config.infrastructure import InfraConfig
from workflows.config.screen import ScreenConfig
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates.candidates import (
    build_load_candidates_template,
    build_shard_candidates_template,
)
from workflows.templates.common.clean_prefix import build_clean_prefix_template
from workflows.templates.common.merge_shards import build_merge_shards_template

WORKFLOW_NAME_PARAM = "{{workflow.name}}"
ITEM_PARAM = "{{item}}"


def _shard_path(prefix: str) -> str:
    return f"{prefix}/shard_id={ITEM_PARAM}"


def _shard_ids(num_shards: int) -> list[int]:
    return list(range(num_shards))


def build_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    candidates_config = screen_config.candidates
    candidate_prefixes = infra_config.storage.prefixes.candidates
    mount_path = LYNCEUS_VOLUME.mount_path
    num_shards = infra_config.candidates.num_shards

    load_candidates_template = build_load_candidates_template(infra_config)
    shard_candidates_template = build_shard_candidates_template(infra_config)
    merge_shards_template = build_merge_shards_template(infra_config)
    clean_prefix_template = build_clean_prefix_template()

    with Workflow(
        generate_name=f"{screen_config.name}-candidates-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(
            name="process-source-dag", inputs=[Parameter(name="source")]
        ) as process_source_dag:
            source_parquet_prefix = (
                f"{candidate_prefixes.raw_parquet}/{{{{inputs.parameters.source}}}}"
            )

            load_task = load_candidates_template(
                name="load-candidates",
                arguments={
                    "source": "{{inputs.parameters.source}}",
                    "mount_path": mount_path,
                    "source_prefix": candidate_prefixes.raw_smiles,
                    "parquet_prefix": source_parquet_prefix,
                },
            )

            shard_task = shard_candidates_template(
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
            process_sources = process_source_dag(
                name="process-sources",
                with_items=candidates_config.sources,
                arguments={"source": ITEM_PARAM},
            )

            merge_shards = merge_shards_template(
                name="merge-shards",
                with_items=_shard_ids(num_shards),
                arguments={
                    "mount_path": mount_path,
                    "input_prefix": _shard_path(f"{candidate_prefixes.shards_staging}"),
                    "output_prefix": _shard_path(candidate_prefixes.shards),
                },
            )

            cleanup_staging = clean_prefix_template(
                name="cleanup-staging",
                arguments={
                    "mount_path": mount_path,
                    "prefix": f"{candidate_prefixes.shards_staging}",
                },
            )

            process_sources >> merge_shards >> cleanup_staging  # type: ignore

    return w
