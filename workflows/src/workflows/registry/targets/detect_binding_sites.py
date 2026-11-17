# workflows/src/workflows/registry/target/detect_binding_sites.py


import re

from hera.workflows import DAG

from workflows.config.core import WorkflowConfigs
from workflows.config.templates import TemplateName
from workflows.templates.builders import TemplateFactory
from workflows.templates.targets import detect_binding_sites_template

DETECT_BINDING_SITES_DAG = "detect-binding-sites-dag"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _task_name(stage: str, ensemble_id: str) -> str:
    return f"{stage}-{_slug(ensemble_id)}"


def _ensemble_prefix(ensembles_prefix: str, ensemble_id: str) -> str:
    return f"{ensembles_prefix}/{ensemble_id}"


def build_detect_binding_sites_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> DAG:
    paths = configs.paths
    targets = configs.screen.targets

    detect_binding_sites = templates.build(
        TemplateName.DETECT_BINDING_SITES, detect_binding_sites_template
    )

    with DAG(name=DETECT_BINDING_SITES_DAG) as detect_binding_sites_dag:
        for ensemble in targets.ensembles:
            ensemble_prefix = _ensemble_prefix(paths.target_ensembles, ensemble.id)

            detect_binding_sites(
                name=_task_name("detect-binding-sites", ensemble.id),
                arguments={
                    "ensemble_path": paths.volume_path(ensemble_prefix),
                    "min_pocket_score": targets.min_pocket_score,
                },
            )

    return detect_binding_sites_dag
