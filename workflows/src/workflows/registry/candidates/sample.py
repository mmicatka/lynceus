# workflows/src/workflows/registry/candidates/sample.py


from hera.workflows import DAG, Task, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    ITEM_PARAM,
    get_template_factory,
    new_workflow,
    shard_filename,
    shard_ids,
)
from workflows.templates import sample_candidates_template
from workflows.templates.builders import TemplateFactory

SAMPLE_CANDIDATES_DAG = "sample-candidates-dag"


def _require_sub_sample(screen_config: ScreenConfig) -> int:
    sub_sample = screen_config.candidates.sub_sample
    if not sub_sample:
        raise RuntimeError(
            "candidates.sub_sample must be set to build the sample workflow"
        )
    return sub_sample


def _subsample_task(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    sub_sample: int,
) -> Task:
    prefixes = infra_config.storage.prefixes.candidates
    num_shards = infra_config.candidates.num_shards
    subsample_candidates = templates.build(
        TemplateName.SUBSAMPLE_CANDIDATES, sample_candidates_template
    )

    return subsample_candidates(
        name="subsample-candidates",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": infra_config.volume.mount_path,
            "source": shard_filename(ITEM_PARAM),
            "source_prefix": prefixes.shards,
            "parquet_prefix": f"{prefixes.shards_sample}/",
            "num_samples": sub_sample // num_shards,
        },
    )


def build_sample_candidates_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    sub_sample = _require_sub_sample(screen_config)

    with DAG(name=SAMPLE_CANDIDATES_DAG) as dag:
        _subsample_task(templates, infra_config, sub_sample)

    return dag


def build_sample_candidates_workflow(
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "candidates-sample") as workflow:
        sample_dag = build_sample_candidates_dag(templates, infra_config, screen_config)

        with DAG(name=ENTRYPOINT_DAG):
            sample_dag(name="sample-candidates")

    return workflow
