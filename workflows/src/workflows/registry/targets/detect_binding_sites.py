# workflows/src/workflows/registry/target/detect_binding_sites.py

import os
import re

from hera.workflows import DAG

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.templates import TemplateFactory
from workflows.templates.targets.detect_binding_sites import (
    detect_binding_sites_template,
)

DETECT_BINDING_SITES_DAG = "detect-binding-sites-dag"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _task_name(stage: str, ensemble_id: str) -> str:
    return f"{stage}-{_slug(ensemble_id)}"


def _ensemble_prefix(ensembles_prefix: str, ensemble_id: str) -> str:
    return f"{ensembles_prefix}/{ensemble_id}"


def build_detect_binding_sites_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    base_path = infra_config.volume.mount_path
    prefixes = infra_config.storage.prefixes.target

    detect_binding_sites = templates.build(
        TemplateName.DETECT_BINDING_SITES, detect_binding_sites_template
    )

    with DAG(name=DETECT_BINDING_SITES_DAG) as detect_binding_sites_dag:
        for ensemble in screen_config.targets.ensembles:
            ensemble_prefix = _ensemble_prefix(prefixes.ensembles, ensemble.id)

            detect_binding_sites(
                name=_task_name("detect-binding-sites", ensemble.id),
                arguments={
                    "ensemble_path": os.path.join(base_path, ensemble_prefix),
                    "min_pocket_score": screen_config.targets.min_pocket_score,
                },
            )

    return detect_binding_sites_dag
