# workflows/src/workflows/registry/candidates/preprocess.py


from collections.abc import Callable
from typing import Any

from hera.workflows import DAG, Parameter, RetryStrategy, Task, Workflow
from hera.workflows.models import ValueFrom

from workflows.config.core import WorkflowConfigs
from workflows.config.paths import SamplePaths
from workflows.config.templates import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    SOURCE_INPUT_NAME,
    SOURCE_PARAM,
    get_template_factory,
    new_workflow,
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
    generate_plan_template,
    preprocess_candidate_shard_template,
    update_manifest_template,
    verify_manifest_template,
)
from workflows.templates.builders import TemplateFactory

PREPROCESS_CANDIDATES_DAG = "preprocess-candidates-dag"
PREPROCESS_FANOUT_DAG = "preprocess-shards-fanout-dag"
PREPROCESS_SHARD_DAG = "preprocess-shard-dag"

SOURCES_PARAM = "sources"
SHARD_FILE_GLOB = "*.parquet"
SHARD_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")

PREPROCESSED_KEY = "preprocessed"
SAMPLE_KEY = "sample"

TaskFactory = Callable[..., Task]


def _sample_paths(configs: WorkflowConfigs) -> SamplePaths:
    return configs.paths.sample(configs.screen.candidates)


def _completed_fields(configs: WorkflowConfigs) -> dict[str, Any]:
    return {SAMPLE_KEY: configs.screen.candidates, PREPROCESSED_KEY: True}


def _sources_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).sources)}}}}"


def _build_plan(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.PLAN_PREPROCESS_CANDIDATES,
        generate_plan_template,
        outputs=[
            Parameter(
                name=MANIFEST_OUTPUT,
                value_from=ValueFrom(path=MANIFEST_PATH),
            )
        ],
    )


def _build_verify_manifest(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.VERIFY_MANIFEST_PREPROCESS_CANDIDATES,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _plan_task(plan: TaskFactory, sample_paths: SamplePaths, when: str) -> Task:
    return plan(
        name="plan-preprocess",
        when=when,
        arguments={
            "base_path": sample_paths.mount_path,
            "input_prefix": sample_paths.raw,
            "source_glob": SHARD_FILE_GLOB,
            "output_file": MANIFEST_PATH,
            "persist_file": sample_paths.preprocessed_manifest,
        },
    )


def _check_manifest_task(
    verify: TaskFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
) -> Task:
    return verify(
        name="check-preprocessed",
        arguments={
            "base_path": sample_paths.mount_path,
            "manifest": sample_paths.preprocessed_manifest,
            "expect": json_arg(_completed_fields(configs)),
            "source_globs": [f"{sample_paths.raw}/{SHARD_FILE_GLOB}"],
            "result_file": MATCHES_PATH,
        },
    )


def _update_manifest_task(
    update: TaskFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
    when: str,
) -> Task:
    return update(
        name="write-manifest",
        when=when,
        arguments={
            "base_path": sample_paths.mount_path,
            "source": sample_paths.preprocessed_manifest,
            "output": sample_paths.preprocessed_manifest,
            "fields": json_arg(_completed_fields(configs)),
        },
    )


def _build_preprocess_shard_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
) -> DAG:
    preprocess_shard = templates.build(
        TemplateName.PREPROCESS_CANDIDATE_SHARD,
        preprocess_candidate_shard_template,
        retry_strategy=SHARD_RETRY,
    )

    with DAG(
        name=PREPROCESS_SHARD_DAG, inputs=[Parameter(name=SOURCE_INPUT_NAME)]
    ) as dag:
        preprocess_shard(
            name="preprocess-shard",
            arguments={
                "base_path": sample_paths.mount_path,
                "source": SOURCE_PARAM,
                "input_prefix": sample_paths.raw,
                "output_prefix": sample_paths.preprocessed_shards,
                "manifest_prefix": sample_paths.preprocessed_manifests,
            },
        )

    return dag


def _build_fanout_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
) -> DAG:
    preprocess_shard_dag = _build_preprocess_shard_dag(templates, sample_paths)

    with DAG(
        name=PREPROCESS_FANOUT_DAG,
        inputs=[Parameter(name=SOURCES_PARAM)],
    ) as dag:
        Task(
            name="preprocess-shards",
            template=preprocess_shard_dag,
            with_param=f"{{{{inputs.parameters.{SOURCES_PARAM}}}}}",
            arguments={SOURCE_INPUT_NAME: ITEM_PARAM},
        )

    return dag


def build_preprocess_candidates_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> DAG:
    sample_paths = _sample_paths(configs)

    with DAG(name=PREPROCESS_CANDIDATES_DAG) as dag:
        verify_manifest = _build_verify_manifest(templates)
        plan = _build_plan(templates)
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST_PREPROCESS_CANDIDATES, update_manifest_template
        )

        check_task = _check_manifest_task(verify_manifest, sample_paths, configs)
        preprocess_gate = when_unmatched(check_task)

        plan_task = _plan_task(plan, sample_paths, preprocess_gate)

        fanout_dag = _build_fanout_dag(templates, sample_paths)
        fanout_task = fanout_dag(
            name="preprocess-shards-fanout",
            when=preprocess_gate,
            arguments={SOURCES_PARAM: _sources_expression(plan_task)},
        )
        write_task = _update_manifest_task(
            update_manifest, sample_paths, configs, preprocess_gate
        )

        check_task >> plan_task >> fanout_task >> write_task  # type: ignore

    return dag


def build_preprocess_candidates_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(configs.screen.name, "preprocess-candidates") as workflow:
        preprocess_dag = build_preprocess_candidates_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            preprocess_dag(name="preprocess-candidates")

    return workflow
