# workflows/src/workflows/registry/surrogate/core.py

from hera.workflows import DAG, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import ENTRYPOINT_DAG, get_template_factory, new_workflow
from workflows.registry.surrogate.sample import build_surrogate_sample_dag


def build_surrogate_sample_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig, round_index: int = 0
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "surrogate-sample") as w:
        sample_dag = build_surrogate_sample_dag(
            templates, infra_config, screen_config, round_index
        )

        with DAG(name=ENTRYPOINT_DAG):
            sample_dag(name="surrogate-sample")

    return w
