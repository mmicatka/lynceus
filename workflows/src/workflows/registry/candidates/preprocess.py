# workflows/src/workflows/registry/candidates/preprocess.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.candidates.common import (
    ENTRYPOINT_DAG,
    candidates_template_factory,
    new_candidates_workflow,
)
from workflows.registry.common import (
    ITEM_PARAM,
    SHARD_PREFIX,
    SHARD_SUFFIX,
    SOURCE_PARAM,
    shard_ids,
)
from workflows.templates import (
    TemplateFactory,
    generate_conformers_template,
    generate_features_template,
)

PREPROCESS_CANDIDATES_DAG = "preprocess-candidates-dag"
PROCESS_SHARD_DAG = "process-shard-dag"


def build_preprocess_candidates_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    base_path = infra_config.volume.mount_path
    num_shards = infra_config.candidates.num_shards
    features = screen_config.filter.features
    candidate_prefixes = infra_config.storage.prefixes.candidates

    generate_conformers = templates.build(
        TemplateName.GENERATE_CONFORMERS, generate_conformers_template
    )
    generate_features = templates.build(
        TemplateName.GENERATE_FEATURES, generate_features_template
    )

    input_prefix = (
        candidate_prefixes.shards_sample
        if screen_config.candidates.sub_sample
        else candidate_prefixes.shards
    )

    with DAG(
        name=PROCESS_SHARD_DAG, inputs=[Parameter(name="source")]
    ) as process_shard_dag:
        conformers_task = generate_conformers(
            name="generate-conformers",
            arguments={
                "base_path": base_path,
                "source": SOURCE_PARAM,
                "input_prefix": input_prefix,
                "output_prefix": candidate_prefixes.conformers,
            },
        )

        features_task = generate_features(
            name="generate-features",
            arguments={
                "base_path": base_path,
                "source": SOURCE_PARAM,
                "input_prefix": candidate_prefixes.conformers,
                "output_prefix": candidate_prefixes.features,
                "features": features,
            },
        )

        conformers_task >> features_task  # type: ignore

    with DAG(name=PREPROCESS_CANDIDATES_DAG) as preprocess_dag:
        process_shard_dag(
            name="process-shards",
            with_items=shard_ids(num_shards),
            arguments={"source": f"{SHARD_PREFIX}{ITEM_PARAM}{SHARD_SUFFIX}"},
        )

    return preprocess_dag


def build_preprocess_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = candidates_template_factory(infra_config)

    with new_candidates_workflow(screen_config.name, "preprocess-candidates") as w:
        preprocess_dag = build_preprocess_candidates_dag(
            templates, infra_config, screen_config
        )

        with DAG(name=ENTRYPOINT_DAG):
            preprocess_dag(name="preprocess-candidates")

    return w
