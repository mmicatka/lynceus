# workflows/src/workflows/registry/candidates/preprocess.py

from hera.workflows import DAG, Parameter, Task, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    SOURCE_INPUT_NAME,
    SOURCE_PARAM,
    get_template_factory,
    new_workflow,
    shard_filename,
    shard_ids,
)
from workflows.templates import (
    TemplateFactory,
    generate_conformers_template,
    generate_features_template,
)

PREPROCESS_CANDIDATES_DAG = "preprocess-candidates-dag"
PROCESS_SHARD_DAG = "process-shard-dag"


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


def _build_process_shard_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    prefixes = infra_config.storage.prefixes.candidates
    base_path = infra_config.volume.mount_path

    generate_conformers = templates.build(
        TemplateName.GENERATE_CONFORMERS, generate_conformers_template
    )
    generate_features = templates.build(
        TemplateName.GENERATE_FEATURES, generate_features_template
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


def build_preprocess_candidates_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    process_shard_dag = _build_process_shard_dag(templates, infra_config, screen_config)

    with DAG(name=PREPROCESS_CANDIDATES_DAG) as dag:
        Task(
            name="process-shards",
            template=process_shard_dag,
            with_items=shard_ids(infra_config.candidates.num_shards),
            arguments={SOURCE_INPUT_NAME: shard_filename(ITEM_PARAM)},
        )

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
            Task(name="preprocess-candidates", template=preprocess_dag)

    return workflow
