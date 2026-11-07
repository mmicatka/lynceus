# workflows/src/workflows/registry/candidates/load.py

from hera.workflows import DAG, Parameter, RetryStrategy, Task, Workflow
from hera.workflows.models import ValueFrom

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    SHARD_FOLDER_PREFIX,
    get_template_factory,
    new_workflow,
    shard_filename,
    shard_ids,
)
from workflows.templates import (
    build_clean_prefix_template,
    merge_shards_template,
    plan_shard_candidates_template,
    shard_candidates_template,
)
from workflows.templates.builders import TemplateFactory

LOAD_CANDIDATES_DAG = "load-candidates-dag"
MANIFEST_OUTPUT = "manifest"
MANIFEST_PATH = "/tmp/manifest.json"
SOURCE_FILE_GLOB = "**/*.smi.gz"
SHARD_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")


def _batches_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).batches)}}}}"


def _clean_staging_task(name: str, infra_config: InfraConfig) -> Task:
    return Task(
        name=name,
        template=build_clean_prefix_template(name),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "prefix": infra_config.storage.prefixes.candidates.shards_staging,
        },
    )


def _plan_shard_task(templates: TemplateFactory, infra_config: InfraConfig) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    plan = templates.build(
        TemplateName.PLAN_SHARD_CANDIDATES,
        plan_shard_candidates_template,
        outputs=[
            Parameter(
                name=MANIFEST_OUTPUT,
                value_from=ValueFrom(path=MANIFEST_PATH),
            )
        ],
    )

    return plan(
        name="plan-shard",
        arguments={
            "source_root": infra_config.volume.mount_path,
            "source_glob": f"{prefixes.raw_smiles}/{SOURCE_FILE_GLOB}",
            "output_file": MANIFEST_PATH,
            "max_batch_gib": str(infra_config.candidates.max_batch_gib),
        },
    )


def _shard_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    plan_task: Task,
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    template_config = infra_config.templates[TemplateName.SHARD_CANDIDATES]
    shard = templates.build(
        TemplateName.SHARD_CANDIDATES,
        shard_candidates_template,
        retry_strategy=SHARD_RETRY,
    )

    return shard(
        name="shard-candidates",
        with_param=_batches_expression(plan_task),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "batch": ITEM_PARAM,
            "output_prefix": prefixes.shards_staging,
            "num_shards": infra_config.candidates.num_shards,
            "scratch_dir": template_config.scratch_path,
        },
    )


def _merge_and_clean_shard_dag(
    templates: TemplateFactory, infra_config: InfraConfig
) -> DAG:
    with DAG(
        name="merge-and-clean-shard",
        inputs=[Parameter(name="shard_id")],
    ) as dag:
        shard_param = "{{inputs.parameters.shard_id}}"
        prefixes = infra_config.storage.prefixes.candidates
        template_config = infra_config.templates[TemplateName.MERGE_SHARDS]

        merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)
        merge = merge_shards(
            name="merge-shard",
            arguments={
                "base_path": infra_config.volume.mount_path,
                "input_path": f"{prefixes.shards_staging}/"
                f"{SHARD_FOLDER_PREFIX}{shard_param}",
                "output_path": f"{prefixes.shards}/{shard_filename(shard_param)}",
                "memory_limit": str(template_config.resources.limits.memory),
            },
        )

        clean = Task(
            name="clean-shard",
            template=build_clean_prefix_template("clean-shard-template"),
            arguments={
                "base_path": infra_config.volume.mount_path,
                "prefix": f"{prefixes.shards_staging}/"
                f"{SHARD_FOLDER_PREFIX}{shard_param}",
            },
        )

        merge >> clean  # type: ignore

    return dag


MERGE_SHARDS_PARALLELISM = 3


def build_merge_shards_dag(
    templates: TemplateFactory, infra_config: InfraConfig
) -> DAG:
    merge_and_clean_dag = _merge_and_clean_shard_dag(templates, infra_config)

    with DAG(
        name="merge-shards-dag",
        parallelism=MERGE_SHARDS_PARALLELISM,
    ) as dag:
        Task(
            name="merge-shards-fanout",
            template=merge_and_clean_dag,
            with_items=shard_ids(infra_config.candidates.num_shards),
            arguments={"shard_id": ITEM_PARAM},
        )

    return dag


def build_load_candidates_dag(
    templates: TemplateFactory, infra_config: InfraConfig, screen_config: ScreenConfig
) -> DAG:
    with DAG(name=LOAD_CANDIDATES_DAG) as dag:
        clean_start_task = _clean_staging_task("clean-staging-start", infra_config)
        plan_task = _plan_shard_task(templates, infra_config)
        shard_task = _shard_task(templates, infra_config, plan_task)

        merge_dag = build_merge_shards_dag(templates, infra_config)
        merge_task = merge_dag(name="merge-shards")

        (
            clean_start_task  # type: ignore
            >> plan_task
            >> shard_task
            >> merge_task
        )

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
