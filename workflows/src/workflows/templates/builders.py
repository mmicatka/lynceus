# workflows/src/workflows/templates/builders.py

from typing import Callable

from hera.workflows import script

from workflows.config import CANDIDATES_IMAGE, InfraConfig
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates.resources import template_resources


def build_template_script(
    infra_config: InfraConfig, template_name: str, func: Callable
) -> Callable:

    template_config = infra_config.templates.get(
        template_name, infra_config.templates.get("default")
    )

    return script(
        image=CANDIDATES_IMAGE,
        resources=template_resources(template_config),
        volumes=[LYNCEUS_VOLUME],
        image_pull_policy="always",
    )(func)
