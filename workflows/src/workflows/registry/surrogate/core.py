# workflows/src/workflows/registry/surrogate/core.py


from hera.workflows import DAG, Workflow

from workflows.config.core import WorkflowConfigs
from workflows.config.templates import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    get_template_factory,
    new_workflow,
)
from workflows.registry.surrogate.sample_site import build_surrogate_site_dag
from workflows.templates.targets.resolve_binding_sites import (
    resolve_binding_sites_template,
)


def build_surrogate_workflow(configs: WorkflowConfigs) -> Workflow:
    templates = get_template_factory(configs.templates)
    paths = configs.paths

    with new_workflow(configs.screen.name, "surrogate") as w:
        resolve_sites = templates.build(
            TemplateName.RESOLVE_BINDING_SITES, resolve_binding_sites_template
        )
        surrogate_site_dag = build_surrogate_site_dag(templates, configs)

        with DAG(name=ENTRYPOINT_DAG):
            resolve_task = resolve_sites(
                name="resolve-sites",
                arguments={
                    "base_path": paths.mount_path,
                    "ensembles_prefix": paths.target_ensembles,
                    "ensemble_ids": [e.id for e in configs.screen.targets.ensembles],
                },
            )
            site_task = surrogate_site_dag(
                name="surrogate-site",
                arguments={
                    "ensemble": "{{item.ensemble}}",
                    "site_id": "{{item.site_id}}",
                    "member_id": "{{item.member_id}}",
                    "center": "{{item.center}}",
                },
                with_param=resolve_task.result,
            )
            resolve_task >> site_task  # type: ignore

    return w
