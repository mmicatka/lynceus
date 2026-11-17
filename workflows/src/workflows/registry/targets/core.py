# workflows/src/workflows/registry/target/core.py


from hera.workflows import DAG, Workflow

from workflows.config.core import WorkflowConfigs
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    get_template_factory,
    new_workflow,
)
from workflows.registry.targets.detect_binding_sites import (
    build_detect_binding_sites_dag,
)
from workflows.registry.targets.load import build_load_targets_dag


def build_targets_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)

    with new_workflow(configs.screen.name, "targets") as workflow:
        download_dag = build_load_targets_dag(templates, configs)
        detect_dag = build_detect_binding_sites_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            load_targets_task = download_dag(name="load-targets")
            detect_sites_task = detect_dag(name="detect-binding-sites")

            load_targets_task >> detect_sites_task  # type: ignore

    return workflow
