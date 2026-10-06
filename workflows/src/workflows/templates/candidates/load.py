# workflows/src/workflows/templates/candidates/load.py


from hera.workflows import script

from workflows.config import InfraConfig
from workflows.config.images import CANDIDATES_IMAGE
from workflows.resources import LYNCEUS_VOLUME
from workflows.templates.common import template_resources

TEMPLATE_NAME = "load_candidates"


def load_candidates(
    source: str, mount_path: str, source_prefix: str, parquet_prefix: str
):
    import os
    import subprocess

    subprocess.run(
        [
            "load-candidates",
            "--input",
            os.path.join(mount_path, source_prefix, source),
            "--output",
            os.path.join(mount_path, parquet_prefix),
        ],
        check=True,
    )


def build_load_candidates_template(infra_config: InfraConfig):
    if TEMPLATE_NAME not in infra_config.templates:
        raise RuntimeError(f"Infrastructure config has no '{TEMPLATE_NAME}' template")

    template_config = infra_config.templates[TEMPLATE_NAME]

    return script(
        image=CANDIDATES_IMAGE,
        resources=template_resources(template_config),
        volumes=[LYNCEUS_VOLUME],
    )(load_candidates)
