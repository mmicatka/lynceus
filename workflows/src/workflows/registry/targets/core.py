# workflows/src/workflows/registry/target/core.py

from hera.workflows import DAG, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import ENTRYPOINT_DAG, get_template_factory, new_workflow
from workflows.registry.targets.detect_binding_sites import (
    build_detect_binding_sites_dag,
)
from workflows.registry.targets.load import build_load_targets_dag


def build_targets_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "targets") as w:
        download_dag = build_load_targets_dag(templates, infra_config, screen_config)
        detect_dag = build_detect_binding_sites_dag(
            templates, infra_config, screen_config
        )

        with DAG(name=ENTRYPOINT_DAG):
            load_targets_task = download_dag(name="load-targets")
            detect_sites_task = detect_dag(name="detect-binding-sites")

            load_targets_task >> detect_sites_task  # type: ignore

    return w
