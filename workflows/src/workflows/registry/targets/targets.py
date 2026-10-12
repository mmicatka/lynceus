# workflows/src/workflows/registry/targets/targets.py

from hera.workflows import Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import new_workflow


def build_targets_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    # templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "candidates-pipeline") as w:
        pass
        # load_dag = build_load_targets(templates, infra_config, screen_config)
        # preprocess_dag = build_preprocess_candidates_dag(
        #     templates, infra_config, screen_config
        # )

        # with DAG(name=ENTRYPOINT_DAG):
        #     load_task = load_dag(name="load-candidates")
        #     preprocess_task = preprocess_dag(name="preprocess-candidates")

        #     load_task >> preprocess_task  # type: ignore

    return w
