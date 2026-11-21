# workflows/src/workflows/registry/candidates/featurize.py


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
    featurize_candidate_shard_template,
    generate_plan_template,
    update_manifest_template,
    verify_manifest_template,
)
from workflows.templates.builders import TemplateFactory

FEATURIZE_CANDIDATES_DAG = "featurize-candidates-dag"
FEATURIZE_FANOUT_DAG = "featurize-shards-fanout-dag"
FEATURIZE_SHARD_DAG = "featurize-shard-dag"

SOURCES_PARAM = "sources"
SHARD_FILE_GLOB = "*.parquet"
SHARD_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")

FEATURIZED_KEY = "featurized"
SAMPLE_KEY = "sample"

TaskFactory = Callable[..., Task]


def _sample_paths(configs: WorkflowConfigs) -> SamplePaths:
    return configs.paths.sample(configs.screen.candidates)


def _completed_fields(configs: WorkflowConfigs) -> dict[str, Any]:
    return {SAMPLE_KEY: configs.screen.candidates, FEATURIZED_KEY: True}


def _sources_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).sources)}}}}"


def _sample_features(configs: WorkflowConfigs) -> list[str]:
    return configs.candidates.samples[configs.screen.candidates].feature_names


def _build_plan(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.PLAN_FEATURIZE_CANDIDATES,
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
        TemplateName.VERIFY_MANIFEST_FEATURIZE_CANDIDATES,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _plan_task(plan: TaskFactory, sample_paths: SamplePaths, when: str) -> Task:
    return plan(
        name="plan-featurize",
        when=when,
        arguments={
            "base_path": sample_paths.mount_path,
            "input_prefix": sample_paths.preprocessed_shards,
            "source_glob": SHARD_FILE_GLOB,
            "output_file": MANIFEST_PATH,
            "persist_file": sample_paths.featurized_manifest,
        },
    )


def _check_manifest_task(
    verify: TaskFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
) -> Task:
    return verify(
        name="check-featurized",
        arguments={
            "base_path": sample_paths.mount_path,
            "manifest": sample_paths.featurized_manifest,
            "expect": json_arg(_completed_fields(configs)),
            "source_globs": [f"{sample_paths.preprocessed_shards}/{SHARD_FILE_GLOB}"],
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
            "source": sample_paths.featurized_manifest,
            "output": sample_paths.featurized_manifest,
            "fields": json_arg(_completed_fields(configs)),
        },
    )


def _build_featurize_shard_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
    features: list[str],
) -> DAG:
    featurize_shard = templates.build(
        TemplateName.FEATURIZE_CANDIDATE_SHARD,
        featurize_candidate_shard_template,
        retry_strategy=SHARD_RETRY,
    )

    with DAG(
        name=FEATURIZE_SHARD_DAG, inputs=[Parameter(name=SOURCE_INPUT_NAME)]
    ) as dag:
        featurize_shard(
            name="featurize-shard",
            arguments={
                "base_path": sample_paths.mount_path,
                "source": SOURCE_PARAM,
                "input_prefix": sample_paths.preprocessed_shards,
                "output_prefix": sample_paths.featurized_shards,
                "manifest_prefix": sample_paths.featurized_manifests,
                "features": features,
            },
        )

    return dag


def _build_fanout_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
    features: list[str],
) -> DAG:
    featurize_shard_dag = _build_featurize_shard_dag(templates, sample_paths, features)
    with DAG(
        name=FEATURIZE_FANOUT_DAG,
        inputs=[Parameter(name=SOURCES_PARAM)],
    ) as dag:
        Task(
            name="featurize-shards",
            template=featurize_shard_dag,
            with_param=f"{{{{inputs.parameters.{SOURCES_PARAM}}}}}",
            arguments={SOURCE_INPUT_NAME: ITEM_PARAM},
        )

    return dag


def build_featurize_candidates_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> DAG:
    sample_paths = _sample_paths(configs)
    features = _sample_features(configs)

    with DAG(name=FEATURIZE_CANDIDATES_DAG) as dag:
        verify_manifest = _build_verify_manifest(templates)
        plan = _build_plan(templates)
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST_FEATURIZE_CANDIDATES, update_manifest_template
        )

        check_task = _check_manifest_task(verify_manifest, sample_paths, configs)
        featurize_gate = when_unmatched(check_task)

        plan_task = _plan_task(plan, sample_paths, featurize_gate)

        fanout_dag = _build_fanout_dag(templates, sample_paths, features)
        fanout_task = fanout_dag(
            name="featurize-shards-fanout",
            when=featurize_gate,
            arguments={SOURCES_PARAM: _sources_expression(plan_task)},
        )
        write_task = _update_manifest_task(
            update_manifest, sample_paths, configs, featurize_gate
        )

        check_task >> plan_task >> fanout_task >> write_task  # type: ignore

    return dag


def build_featurize_candidates_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(
        configs.screen.name,
        "featurize-candidates",
        priority=configs.priority,
        pod_priority_class_name=configs.pod_priority_class_name,
    ) as workflow:
        featurize_dag = build_featurize_candidates_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            featurize_dag(name="featurize-candidates")

    return workflow
