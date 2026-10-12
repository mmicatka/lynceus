# workflows/src/workflows/registry/targets/targets.py

from hera.workflows import DAG, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import ENTRYPOINT_DAG, get_template_factory, new_workflow
from workflows.registry.targets.load import build_load_targets_dag


def build_targets_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "download-pdbs") as w:
        download_dag = build_load_targets_dag(templates, infra_config, screen_config)

        with DAG(name=ENTRYPOINT_DAG):
            download_dag(name="download-pdbs")

    return w
