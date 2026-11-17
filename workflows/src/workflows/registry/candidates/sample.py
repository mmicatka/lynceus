# workflows/src/workflows/registry/candidates/sample.py


from hera.workflows import DAG, RetryStrategy, Task, Workflow

from workflows.config.core import WorkflowConfigs
from workflows.config.templates import TemplateName
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

SAMPLE_SHARDS_PARALLELISM = 5
SAMPLE_RETRY = RetryStrategy(limit=3, retry_policy="OnFailure")
SAMPLE_CANDIDATES_DAG = "sample-candidates-dag"


def _sample_spec(configs: WorkflowConfigs) -> tuple[str, int]:
    sample_name = configs.screen.candidates
    sample_cfg = configs.candidates.samples.get(sample_name)
    if sample_cfg is None:
        raise RuntimeError(
            f"Unknown sample {sample_name!r}; "
            f"available: {sorted(configs.candidates.samples)}"
        )
    return sample_name, sample_cfg.num_samples


def _subsample_task(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> Task:
    sample_name, sub_sample = _sample_spec(configs)
    paths = configs.paths
    sample_paths = paths.sample(sample_name)
    num_shards = configs.candidates.candidate_pool.sharding.num_shards

    subsample_candidates = templates.build(
        TemplateName.SUBSAMPLE_CANDIDATES,
        sample_candidates_template,
        retry_strategy=SAMPLE_RETRY,
    )

    return subsample_candidates(
        name="subsample-candidates",
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": paths.mount_path,
            "source": shard_filename(ITEM_PARAM),
            "source_prefix": paths.merged,
            "parquet_prefix": f"{sample_paths.raw}/",
            "num_samples": sub_sample // num_shards,
        },
    )


def build_sample_candidates_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
    parallelism: int = SAMPLE_SHARDS_PARALLELISM,
) -> DAG:
    with DAG(name=SAMPLE_CANDIDATES_DAG, parallelism=parallelism) as dag:
        _subsample_task(templates, configs)

    return dag


def build_sample_candidates_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(configs.screen.name, "candidates-sample") as workflow:
        sample_dag = build_sample_candidates_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            sample_dag(name="sample-candidates")

    return workflow
