# workflows/src/workflows/registry/candidates/load.py


import json
from typing import Any

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
    update_manifest_template,
    verify_manifest_template,
    verify_shard_layout_template,
)
from workflows.templates.builders import TemplateFactory

LOAD_CANDIDATES_DAG = "load-candidates-dag"
MANIFEST_OUTPUT = "manifest"
MANIFEST_PATH = "/tmp/manifest.json"
SOURCE_FILE_GLOB = "**/*.smi.gz"
SHARD_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")

BATCHES_PARAM = "batches"
SHARD_PARALLELISM = 8
MERGE_SHARDS_PARALLELISM = 2

PLAN_FILENAME = "load_plan.json"
MANIFEST_FILENAME = "candidate_shards.manifest.json"
MATCHES_OUTPUT = "matches"
MATCHES_PATH = "/tmp/manifest_matches.txt"
SCHEME_VERSION = "zinc22-id-hash-mod-v1"
ID_PLACEHOLDER = "{id}"

NUM_SHARDS_KEY = "num_shards"
SCHEME_KEY = "scheme"
SHARDED_KEY = "sharded"
MERGED_KEY = "merged"

CHECK_FINAL_IN_RANGE = "final-shards-in-range"
CHECK_STAGING_COMPLETE = "staging-complete"
CHECK_MERGE_COMPLETE = "merge-complete"


def _volume_path(infra_config: InfraConfig, relative: str) -> str:
    return f"{infra_config.volume.mount_path}/{relative}"


def _state_path(infra_config: InfraConfig, filename: str) -> str:
    state_prefix = infra_config.storage.prefixes.candidates.shards_manifests
    return _volume_path(infra_config, f"{state_prefix}/{filename}")


def _json_arg(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _manifest_fields(infra_config: InfraConfig) -> dict[str, Any]:
    return {
        NUM_SHARDS_KEY: infra_config.candidates.num_shards,
        SCHEME_KEY: SCHEME_VERSION,
    }


def _when_unmatched(check_task: Task) -> str:
    result = f"tasks.{check_task.name}.outputs.parameters.{MATCHES_OUTPUT}"
    return f"{{{{{result}}}}} == false"


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
            "persist_file": _state_path(infra_config, PLAN_FILENAME),
        },
    )


def _shard_task(templates: TemplateFactory, infra_config: InfraConfig) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    template_config = infra_config.templates[TemplateName.SHARD_CANDIDATES]
    shard = templates.build(
        TemplateName.SHARD_CANDIDATES,
        shard_candidates_template,
        retry_strategy=SHARD_RETRY,
    )

    return shard(
        name="shard-candidates",
        with_param=f"{{{{inputs.parameters.{BATCHES_PARAM}}}}}",
        arguments={
            "base_path": infra_config.volume.mount_path,
            "batch": ITEM_PARAM,
            "output_prefix": prefixes.shards_staging,
            "num_shards": infra_config.candidates.num_shards,
            "scratch_dir": template_config.scratch_path,
        },
    )


def build_shard_dag(templates: TemplateFactory, infra_config: InfraConfig) -> DAG:
    with DAG(
        name="shard-candidates-dag",
        inputs=[Parameter(name=BATCHES_PARAM)],
        parallelism=SHARD_PARALLELISM,
    ) as dag:
        _shard_task(templates, infra_config)

    return dag


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


def _build_verify_manifest(templates: TemplateFactory):
    return templates.build(
        TemplateName.VERIFY_CANDIDATES_MANIFEST,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _check_manifest_task(
    verify, infra_config: InfraConfig, name: str, completion_key: str
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    expected = {**_manifest_fields(infra_config), completion_key: True}
    return verify(
        name=name,
        arguments={
            "base_path": infra_config.volume.mount_path,
            "manifest": _state_path(infra_config, MANIFEST_FILENAME),
            "expect": _json_arg(expected),
            "source_glob": f"{prefixes.raw_smiles}/{SOURCE_FILE_GLOB}",
            "result_file": MATCHES_PATH,
        },
    )


def _layout_task(
    verify_layout, infra_config: InfraConfig, name: str, check: str, when: str
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    return verify_layout(
        name=name,
        when=when,
        arguments={
            "base_path": infra_config.volume.mount_path,
            "check": check,
            "num_shards": str(infra_config.candidates.num_shards),
            "filename_template": shard_filename(ID_PLACEHOLDER),
            "folder_prefix": SHARD_FOLDER_PREFIX,
            "shards_dir": prefixes.shards,
            "staging_dir": prefixes.shards_staging,
        },
    )


def _update_manifest_task(
    update,
    infra_config: InfraConfig,
    name: str,
    source: str,
    fields: dict[str, Any],
    when: str,
) -> Task:
    return update(
        name=name,
        when=when,
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": source,
            "output": _state_path(infra_config, MANIFEST_FILENAME),
            "fields": _json_arg(fields),
        },
    )


def build_load_candidates_dag(
    templates: TemplateFactory, infra_config: InfraConfig, screen_config: ScreenConfig
) -> DAG:
    manifest_path = _state_path(infra_config, MANIFEST_FILENAME)

    with DAG(name=LOAD_CANDIDATES_DAG) as dag:
        verify_manifest = _build_verify_manifest(templates)
        verify_layout = templates.build(
            TemplateName.VERIFY_SHARD_LAYOUT, verify_shard_layout_template
        )
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST, update_manifest_template
        )

        plan_task = _plan_shard_task(templates, infra_config)
        check_sharded = _check_manifest_task(
            verify_manifest, infra_config, "check-sharded", SHARDED_KEY
        )
        check_merged = _check_manifest_task(
            verify_manifest, infra_config, "check-merged", MERGED_KEY
        )
        shard_gate = _when_unmatched(check_sharded)
        merge_gate = _when_unmatched(check_merged)

        guard_task = _layout_task(
            verify_layout,
            infra_config,
            "verify-final-shards",
            CHECK_FINAL_IN_RANGE,
            shard_gate,
        )
        shard_dag = build_shard_dag(templates, infra_config)
        shard_task = shard_dag(
            name="shard-candidates",
            when=shard_gate,
            arguments={BATCHES_PARAM: _batches_expression(plan_task)},
        )
        staging_task = _layout_task(
            verify_layout,
            infra_config,
            "verify-staging",
            CHECK_STAGING_COMPLETE,
            shard_gate,
        )
        write_task = _update_manifest_task(
            update_manifest,
            infra_config,
            "write-manifest",
            _state_path(infra_config, PLAN_FILENAME),
            {**_manifest_fields(infra_config), SHARDED_KEY: True},
            shard_gate,
        )

        merge_dag = build_merge_shards_dag(templates, infra_config)
        merge_task = merge_dag(name="merge-shards", when=merge_gate)
        merged_task = _layout_task(
            verify_layout,
            infra_config,
            "verify-merged",
            CHECK_MERGE_COMPLETE,
            merge_gate,
        )
        mark_task = _update_manifest_task(
            update_manifest,
            infra_config,
            "mark-merged",
            manifest_path,
            {MERGED_KEY: True},
            merge_gate,
        )
        clean_end_task = _clean_staging_task("clean-staging-end", infra_config)

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
