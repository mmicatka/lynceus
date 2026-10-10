# workflows/src/workflows/register/candidates/preprocess_candidates.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import ImageName, TemplateName
from workflows.registry.common import (
    ITEM_PARAM,
    SERVICE_ACCOUNT_NAME,
    SHARD_PREFIX,
    SOURCE_PARAM,
    shard_ids,
)
from workflows.resources.retry import IO_RETRY_STRATEGY
from workflows.templates import (
    TemplateFactory,
    generate_conformers_template,
    generate_features_template,
)

SHARD_SUFFIX = ".parquet"


def build_preprocess_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = TemplateFactory.from_config(
        infra_config, ImageName.CANDIDATES, retry_strategy=IO_RETRY_STRATEGY
    )
    candidate_prefixes = infra_config.storage.prefixes.candidates
    mount_path = infra_config.volume.mount_path
    num_shards = infra_config.candidates.num_shards
    features = screen_config.filter.features

    generate_conformers = templates.build(
        TemplateName.GENERATE_CONFORMERS, generate_conformers_template
    )
    generate_features = templates.build(
        TemplateName.GENERATE_FEATURES, generate_features_template
    )

    with Workflow(
        generate_name=f"{screen_config.name}-preprocess-candidates-",
        entrypoint="main-dag",
        service_account_name=SERVICE_ACCOUNT_NAME,
    ) as w:
        with DAG(
            name="process-shard-dag", inputs=[Parameter(name="source")]
        ) as process_shard_dag:
            conformers_task = generate_conformers(
                name="generate-conformers",
                arguments={
                    "source": SOURCE_PARAM,
                    "mount_path": mount_path,
                    "input_prefix": candidate_prefixes.shards,
                    "output_prefix": candidate_prefixes.conformers,
                },
            )

            features_task = generate_features(
                name="generate-features",
                arguments={
                    "source": SOURCE_PARAM,
                    "mount_path": mount_path,
                    "input_prefix": candidate_prefixes.conformers,
                    "output_prefix": candidate_prefixes.features,
                    "features": features,
                },
            )

            conformers_task >> features_task  # type: ignore

        with DAG(name="main-dag"):
            process_shard_dag(
                name="process-shards",
                with_items=shard_ids(num_shards),
                arguments={"source": f"{SHARD_PREFIX}{ITEM_PARAM}{SHARD_SUFFIX}"},
            )

    return w
