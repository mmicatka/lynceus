# workflows/src/workflows/registry/candidates/preprocess.py

from typing import Any

from hera.workflows import DAG, Parameter, RetryStrategy, Task, Workflow
from hera.workflows.models import ValueFrom

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
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
    TemplateFactory,
    generate_conformers_template,
    generate_features_template,
    plan_preprocess_candidates_template,
    update_manifest_template,
    verify_manifest_template,
)

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
SUB_SAMPLE_KEY = "sub_sample"


def _conformer_input_prefix(
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> str:
    prefixes = infra_config.storage.prefixes.candidates
    return (
        prefixes.shards_sample
        if screen_config.candidates.sub_sample
        else prefixes.shards
    )


def _state_path(infra_config: InfraConfig, filename: str) -> str:
    state_prefix = infra_config.storage.prefixes.candidates.shards_manifests
    return f"{infra_config.volume.mount_path}/{state_prefix}/{filename}"


def _manifest_fields(screen_config: ScreenConfig) -> dict[str, Any]:
    return {
        SUB_SAMPLE_KEY: screen_config.candidates.sub_sample,
        FEATURES_KEY: list(screen_config.filter.feature_list),
    }


def _sources_expression(plan_task: Task) -> str:
    manifest = f"tasks['{plan_task.name}'].outputs.parameters.{MANIFEST_OUTPUT}"
    return f"{{{{=toJson(fromJSON({manifest}).sources)}}}}"


def _plan_preprocess_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Task:
    input_prefix = _conformer_input_prefix(infra_config, screen_config)
    state_prefix = infra_config.storage.prefixes.candidates.shards_manifests
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
            "base_path": infra_config.volume.mount_path,
            "input_prefix": input_prefix,
            "source_glob": SHARD_FILE_GLOB,
            "output_file": MANIFEST_PATH,
            "persist_file": f"{state_prefix}/{PLAN_FILENAME}",
        },
    )


def _build_verify_manifest(templates: TemplateFactory):
    return templates.build(
        TemplateName.VERIFY_MANIFEST_PREPROCESS_CANDIDATES,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _check_manifest_task(
    verify,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Task:
    input_prefix = _conformer_input_prefix(infra_config, screen_config)
    expected = {**_manifest_fields(screen_config), PREPROCESSED_KEY: True}
    return verify(
        name="check-preprocessed",
        arguments={
            "base_path": infra_config.volume.mount_path,
            "manifest": _state_path(infra_config, MANIFEST_FILENAME),
            "expect": json_arg(expected),
            "source_globs": [f"{input_prefix}/{SHARD_FILE_GLOB}"],
            "result_file": MATCHES_PATH,
        },
    )


def _update_manifest_task(
    update,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
    when: str,
) -> Task:
    return update(
        name="write-manifest",
        when=when,
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": _state_path(infra_config, PLAN_FILENAME),
            "output": _state_path(infra_config, MANIFEST_FILENAME),
            "fields": json_arg(
                {**_manifest_fields(screen_config), PREPROCESSED_KEY: True}
            ),
        },
    )


def _build_process_shard_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    prefixes = infra_config.storage.prefixes.candidates
    base_path = infra_config.volume.mount_path

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
                "base_path": base_path,
                "source": SOURCE_PARAM,
                "input_prefix": _conformer_input_prefix(infra_config, screen_config),
                "output_prefix": prefixes.conformers,
            },
        )
        features_task = generate_features(
            name="generate-features",
            arguments={
                "base_path": base_path,
                "source": SOURCE_PARAM,
                "input_prefix": prefixes.conformers,
                "output_prefix": prefixes.features,
                "features": screen_config.filter.feature_list,
            },
        )
        conformers_task >> features_task  # type: ignore

    return dag


def _build_fanout_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    process_shard_dag = _build_process_shard_dag(templates, infra_config, screen_config)

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
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    with DAG(name=PREPROCESS_CANDIDATES_DAG) as dag:
        verify_manifest = _build_verify_manifest(templates)
        update_manifest = templates.build(
            TemplateName.UPDATE_MANIFEST_PREPROCESS_CANDIDATES, update_manifest_template
        )

        plan_task = _plan_preprocess_task(templates, infra_config, screen_config)
        check_task = _check_manifest_task(verify_manifest, infra_config, screen_config)
        preprocess_gate = when_unmatched(check_task)

        fanout_dag = _build_fanout_dag(templates, infra_config, screen_config)
        fanout_task = fanout_dag(
            name="process-shards-fanout",
            when=preprocess_gate,
            arguments={SOURCES_PARAM: _sources_expression(plan_task)},
        )
        write_task = _update_manifest_task(
            update_manifest, infra_config, screen_config, preprocess_gate
        )

        plan_task >> check_task >> fanout_task >> write_task  # type: ignore

    return dag


def build_preprocess_candidates_workflow(
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "preprocess-candidates") as workflow:
        preprocess_dag = build_preprocess_candidates_dag(
            templates, infra_config, screen_config
        )

        with DAG(name=ENTRYPOINT_DAG):
            preprocess_dag(name="preprocess-candidates")

    return workflow
