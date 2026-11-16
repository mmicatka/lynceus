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
    generate_conformers_template,
    generate_features_template,
    plan_preprocess_candidates_template,
    update_manifest_template,
    verify_manifest_template,
)
from workflows.templates.builders import TemplateFactory

PREPROCESS_CANDIDATES_DAG = "preprocess-candidates-dag"
PREPROCESS_FANOUT_DAG = "preprocess-shards-fanout-dag"
PROCESS_SHARD_DAG = "process-shard-dag"

SOURCES_PARAM = "sources"
SHARD_FILE_GLOB = "*.parquet"
SHARD_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")

PLAN_FILENAME = "preprocess_plan.json"
MANIFEST_FILENAME = "preprocess_candidates.manifest.json"
PREPROCESSED_KEY = "preprocessed"
FEATURES_KEY = "features"
SAMPLE_KEY = "sample"

TaskFactory = Callable[..., Task]


def _sample_paths(configs: WorkflowConfigs) -> SamplePaths:
    return configs.paths.sample(configs.screen.candidates)


def _manifest_fields(configs: WorkflowConfigs) -> dict[str, Any]:
    sample_name = configs.screen.candidates
    sample = configs.candidates.samples[sample_name]
    return {
        SAMPLE_KEY: sample_name,
        FEATURES_KEY: [feature.value for feature in sample.feature_types],
    }


def _sources_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).sources)}}}}"


def _plan_preprocess_task(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
) -> Task:
    plan = templates.build(
        TemplateName.PLAN_PREPROCESS_CANDIDATES,
        plan_preprocess_candidates_template,
        outputs=[
            Parameter(
                name=MANIFEST_OUTPUT,
                value_from=ValueFrom(path=MANIFEST_PATH),
            )
        ],
    )

    return plan(
        name="plan-preprocess",
        arguments={
            "base_path": sample_paths.mount_path,
            "input_prefix": sample_paths.shards_sample,
            "source_glob": SHARD_FILE_GLOB,
            "output_file": MANIFEST_PATH,
            "persist_file": f"{sample_paths.manifests}/{PLAN_FILENAME}",
        },
    )


def _build_verify_manifest(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.VERIFY_MANIFEST_PREPROCESS_CANDIDATES,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _check_manifest_task(
    verify: TaskFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
) -> Task:
    expected = {**_manifest_fields(configs), PREPROCESSED_KEY: True}
    return verify(
        name="check-preprocessed",
        arguments={
            "base_path": sample_paths.mount_path,
            "manifest": sample_paths.state_path(MANIFEST_FILENAME),
            "expect": json_arg(expected),
            "source_globs": [f"{sample_paths.shards_sample}/{SHARD_FILE_GLOB}"],
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
            "source": sample_paths.state_path(PLAN_FILENAME),
            "output": sample_paths.state_path(MANIFEST_FILENAME),
            "fields": json_arg({**_manifest_fields(configs), PREPROCESSED_KEY: True}),
        },
    )


def _build_process_shard_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
) -> DAG:
    generate_conformers = templates.build(
        TemplateName.GENERATE_CONFORMERS,
        generate_conformers_template,
        retry_strategy=SHARD_RETRY,
    )
    generate_features = templates.build(
        TemplateName.GENERATE_FEATURES,
        generate_features_template,
        retry_strategy=SHARD_RETRY,
    )

    with DAG(name=PROCESS_SHARD_DAG, inputs=[Parameter(name=SOURCE_INPUT_NAME)]) as dag:
        conformers_task = generate_conformers(
            name="generate-conformers",
            arguments={
                "base_path": sample_paths.mount_path,
                "source": SOURCE_PARAM,
                "input_prefix": sample_paths.shards_sample,
                "output_prefix": sample_paths.conformers,
            },
        )
        sample = configs.candidates.samples[configs.screen.candidates]
        features_task = generate_features(
            name="generate-features",
            arguments={
                "base_path": sample_paths.mount_path,
                "source": SOURCE_PARAM,
                "input_prefix": sample_paths.conformers,
                "output_prefix": sample_paths.features,
                "features": [feature.value for feature in sample.feature_types],
            },
        )
        conformers_task >> features_task  # type: ignore

    return dag


def _build_fanout_dag(
    templates: TemplateFactory,
    sample_paths: SamplePaths,
    configs: WorkflowConfigs,
) -> DAG:
    process_shard_dag = _build_process_shard_dag(templates, sample_paths, configs)

    with DAG(
        name=PREPROCESS_FANOUT_DAG,
        inputs=[Parameter(name=SOURCES_PARAM)],
    ) as dag:
        Task(
            name="process-shards",
            template=process_shard_dag,
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
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST_PREPROCESS_CANDIDATES, update_manifest_template
        )

        plan_task = _plan_preprocess_task(templates, sample_paths)
        check_task = _check_manifest_task(verify_manifest, sample_paths, configs)
        preprocess_gate = when_unmatched(check_task)

        fanout_dag = _build_fanout_dag(templates, sample_paths, configs)
        fanout_task = fanout_dag(
            name="process-shards-fanout",
            when=preprocess_gate,
            arguments={SOURCES_PARAM: _sources_expression(plan_task)},
        )
        write_task = _update_manifest_task(
            update_manifest, sample_paths, configs, preprocess_gate
        )

        plan_task >> check_task >> fanout_task >> write_task  # type: ignore

    return dag


def build_preprocess_candidates_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(configs.screen.name, "preprocess-candidates") as workflow:
        preprocess_dag = build_preprocess_candidates_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            preprocess_dag(name="preprocess-candidates")

    return workflow
