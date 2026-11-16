# workflows/src/workflows/registry/candidates/load.py


# workflows/src/workflows/registry/candidates/load.py

from collections.abc import Callable
from typing import Any

from hera.workflows import DAG, Parameter, Task, Workflow
from hera.workflows.models import ValueFrom

from workflows.config.candidates import ShardingConfig
from workflows.config.core import WorkflowConfigs
from workflows.config.paths import WorkflowPaths
from workflows.config.templates import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    SHARD_FOLDER_PREFIX,
    get_template_factory,
    new_workflow,
    shard_filename,
    shard_ids,
)
from workflows.registry.common.manifest_gate import (
    MANIFEST_OUTPUT,
    MANIFEST_PATH,
    MATCHES_OUTPUT,
    MATCHES_PATH,
    json_arg,
    when_unmatched,
)
from workflows.templates import (
    build_clean_prefix_template,
    merge_shards_template,
    plan_shard_candidates_template,
    shard_candidates_template,
    update_manifest_template,
    verify_manifest_template,
    verify_shard_layout_template,
)
from workflows.templates.builders import TemplateFactory

LOAD_CANDIDATES_DAG = "load-candidates-dag"
SOURCE_FILE_GLOB = "**/*.smi.gz"

BATCHES_PARAM = "batches"
SHARD_PARALLELISM = 8
MERGE_SHARDS_PARALLELISM = 1

PLAN_FILENAME = "load_plan.json"
MANIFEST_FILENAME = "candidate_shards.manifest.json"
SCHEME_VERSION = "zinc22-id-hash-mod-v1"
ID_PLACEHOLDER = "{id}"

NUM_SHARDS_KEY = "num_shards"
SCHEME_KEY = "scheme"
SHARDED_KEY = "sharded"
MERGED_KEY = "merged"

CHECK_FINAL_IN_RANGE = "final-shards-in-range"
CHECK_STAGING_COMPLETE = "staging-complete"
CHECK_MERGE_COMPLETE = "merge-complete"

TaskFactory = Callable[..., Task]


def _manifest_fields(sharding: ShardingConfig) -> dict[str, Any]:
    return {
        NUM_SHARDS_KEY: sharding.num_shards,
        SCHEME_KEY: SCHEME_VERSION,
    }


def _batches_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).batches)}}}}"


def _clean_staging_task(name: str, paths: WorkflowPaths) -> Task:
    return Task(
        name=name,
        template=build_clean_prefix_template(name),
        arguments={
            "base_path": paths.mount_path,
            "prefix": paths.staging,
        },
    )


def _plan_shard_task(
    templates: TemplateFactory, paths: WorkflowPaths, sharding: ShardingConfig
) -> Task:
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
            "source_root": paths.mount_path,
            "source_glob": f"{paths.smiles}/{SOURCE_FILE_GLOB}",
            "output_file": MANIFEST_PATH,
            "max_batch_gib": str(sharding.max_batch_gib),
            "persist_file": paths.state_path(PLAN_FILENAME),
        },
    )


def _shard_task(
    templates: TemplateFactory,
    paths: WorkflowPaths,
    sharding: ShardingConfig,
    scratch_dir: str,
) -> Task:
    shard = templates.build(
        TemplateName.SHARD_CANDIDATES,
        shard_candidates_template,
    )

    return shard(
        name="shard-candidates",
        with_param=f"{{{{inputs.parameters.{BATCHES_PARAM}}}}}",
        arguments={
            "base_path": paths.mount_path,
            "batch": ITEM_PARAM,
            "output_prefix": paths.staging,
            "num_shards": sharding.num_shards,
            "scratch_dir": scratch_dir,
        },
    )


def build_shard_dag(templates: TemplateFactory, configs: WorkflowConfigs) -> DAG:
    scratch_dir = configs.templates.template(TemplateName.SHARD_CANDIDATES).scratch_path

    with DAG(
        name="shard-candidates-dag",
        inputs=[Parameter(name=BATCHES_PARAM)],
        parallelism=SHARD_PARALLELISM,
    ) as dag:
        _shard_task(
            templates,
            configs.paths,
            configs.candidates.candidate_pool.sharding,
            scratch_dir,
        )

    return dag


def _merge_and_clean_shard_dag(
    templates: TemplateFactory, paths: WorkflowPaths, memory_limit: str
) -> DAG:
    with DAG(
        name="merge-and-clean-shard",
        inputs=[Parameter(name="shard_id")],
    ) as dag:
        shard_param = "{{inputs.parameters.shard_id}}"
        staging_shard_dir = f"{paths.staging}/{SHARD_FOLDER_PREFIX}{shard_param}"

        merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)
        merge = merge_shards(
            name="merge-shard",
            arguments={
                "base_path": paths.mount_path,
                "input_path": staging_shard_dir,
                "output_path": f"{paths.merged}/{shard_filename(shard_param)}",
                "memory_limit": memory_limit,
            },
        )

        clean = Task(
            name="clean-shard",
            template=build_clean_prefix_template("clean-shard-template"),
            arguments={
                "base_path": paths.mount_path,
                "prefix": staging_shard_dir,
            },
        )

        merge >> clean  # type: ignore

    return dag


def build_merge_shards_dag(templates: TemplateFactory, configs: WorkflowConfigs) -> DAG:
    memory_limit = configs.templates.template(
        TemplateName.MERGE_SHARDS
    ).resources.limits.memory
    merge_and_clean_dag = _merge_and_clean_shard_dag(
        templates, configs.paths, memory_limit
    )
    num_shards = configs.candidates.candidate_pool.sharding.num_shards

    with DAG(
        name="merge-shards-dag",
        parallelism=MERGE_SHARDS_PARALLELISM,
    ) as dag:
        Task(
            name="merge-shards-fanout",
            template=merge_and_clean_dag,
            with_items=shard_ids(num_shards),
            arguments={"shard_id": ITEM_PARAM},
        )

    return dag


def _build_verify_manifest(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.VERIFY_MANIFEST_LOAD_CANDIDATES,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _check_manifest_task(
    verify: TaskFactory,
    paths: WorkflowPaths,
    sharding: ShardingConfig,
    name: str,
    completion_key: str,
) -> Task:
    expected = {**_manifest_fields(sharding), completion_key: True}
    return verify(
        name=name,
        arguments={
            "base_path": paths.mount_path,
            "manifest": paths.state_path(MANIFEST_FILENAME),
            "expect": json_arg(expected),
            "source_globs": [f"{paths.smiles}/{SOURCE_FILE_GLOB}"],
            "result_file": MATCHES_PATH,
        },
    )


def _layout_task(
    verify_layout: TaskFactory,
    paths: WorkflowPaths,
    sharding: ShardingConfig,
    name: str,
    check: str,
    when: str,
) -> Task:
    return verify_layout(
        name=name,
        when=when,
        arguments={
            "base_path": paths.mount_path,
            "check": check,
            "num_shards": str(sharding.num_shards),
            "filename_template": shard_filename(ID_PLACEHOLDER),
            "folder_prefix": SHARD_FOLDER_PREFIX,
            "shards_dir": paths.merged,
            "staging_dir": paths.staging,
        },
    )


def _update_manifest_task(
    update: TaskFactory,
    paths: WorkflowPaths,
    name: str,
    source: str,
    fields: dict[str, Any],
    when: str,
) -> Task:
    return update(
        name=name,
        when=when,
        arguments={
            "base_path": paths.mount_path,
            "source": source,
            "output": paths.state_path(MANIFEST_FILENAME),
            "fields": json_arg(fields),
        },
    )


def build_load_candidates_dag(
    templates: TemplateFactory, configs: WorkflowConfigs
) -> DAG:
    paths = configs.paths
    sharding = configs.candidates.candidate_pool.sharding
    manifest_path = paths.state_path(MANIFEST_FILENAME)

    with DAG(name=LOAD_CANDIDATES_DAG) as dag:
        verify_manifest = _build_verify_manifest(templates)
        verify_layout = templates.build(
            TemplateName.VERIFY_SHARD_LAYOUT, verify_shard_layout_template
        )
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST_LOAD_CANDIDATES, update_manifest_template
        )

        plan_task = _plan_shard_task(templates, paths, sharding)
        check_sharded = _check_manifest_task(
            verify_manifest, paths, sharding, "check-sharded", SHARDED_KEY
        )
        check_merged = _check_manifest_task(
            verify_manifest, paths, sharding, "check-merged", MERGED_KEY
        )
        shard_gate = when_unmatched(check_sharded)
        merge_gate = when_unmatched(check_merged)

        guard_task = _layout_task(
            verify_layout,
            paths,
            sharding,
            "verify-final-shards",
            CHECK_FINAL_IN_RANGE,
            shard_gate,
        )
        shard_dag = build_shard_dag(templates, configs)
        shard_task = shard_dag(
            name="shard-candidates",
            when=shard_gate,
            arguments={BATCHES_PARAM: _batches_expression(plan_task)},
        )
        staging_task = _layout_task(
            verify_layout,
            paths,
            sharding,
            "verify-staging",
            CHECK_STAGING_COMPLETE,
            shard_gate,
        )
        write_task = _update_manifest_task(
            update_manifest,
            paths,
            "write-manifest",
            paths.state_path(PLAN_FILENAME),
            {**_manifest_fields(sharding), SHARDED_KEY: True},
            shard_gate,
        )

        merge_dag = build_merge_shards_dag(templates, configs)
        merge_task = merge_dag(name="merge-shards", when=merge_gate)
        merged_task = _layout_task(
            verify_layout,
            paths,
            sharding,
            "verify-merged",
            CHECK_MERGE_COMPLETE,
            merge_gate,
        )
        mark_task = _update_manifest_task(
            update_manifest,
            paths,
            "mark-merged",
            manifest_path,
            {MERGED_KEY: True},
            merge_gate,
        )
        clean_end_task = _clean_staging_task("clean-staging-end", paths)

        plan_task >> [check_sharded, check_merged]  # type: ignore
        (
            check_sharded  # type: ignore
            >> guard_task
            >> shard_task
            >> staging_task
            >> write_task
            >> merge_task
        )
        check_merged >> merge_task  # type: ignore
        merge_task >> merged_task >> mark_task >> clean_end_task  # type: ignore

    return dag


def build_load_candidates_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(configs.screen.name, "candidates") as workflow:
        load_dag = build_load_candidates_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            load_dag(name="load-candidates")

    return workflow
