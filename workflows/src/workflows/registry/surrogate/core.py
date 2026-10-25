# workflows/src/workflows/registry/surrogate/core.py

from hera.workflows import DAG, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.registry.common.core import (
    ENTRYPOINT_DAG,
    get_template_factory,
    new_workflow,
)
from workflows.registry.surrogate.sample_site import build_surrogate_site_dag
from workflows.templates.targets.resolve_binding_sites import (
    resolve_binding_sites_template,
)


def build_surrogate_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "surrogate") as w:
        resolve_sites = templates.build(
            TemplateName.RESOLVE_BINDING_SITES, resolve_binding_sites_template
        )
        surrogate_site_dag = build_surrogate_site_dag(
            templates, infra_config, screen_config
        )

        with DAG(name=ENTRYPOINT_DAG):
            resolve_task = resolve_sites(
                name="resolve-sites",
                arguments={
                    "base_path": infra_config.volume.mount_path,
                    "ensembles_prefix": infra_config.storage.prefixes.target.ensembles,
                    "ensemble_ids": [e.id for e in screen_config.targets.ensembles],
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
