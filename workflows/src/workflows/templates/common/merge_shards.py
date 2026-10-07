# workflows/src/workflows/templates/common/merge_shards.py

from hera.workflows import script

from workflows.config import InfraConfig
from workflows.config.images import CANDIDATES_IMAGE
from workflows.resources import LYNCEUS_VOLUME
from workflows.templates.resources import template_resources

TEMPLATE_NAME = "merge_shards"


def merge_shards(
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "merge-shards",
            "--input",
            os.path.join(mount_path, input_prefix),
            "--output",
            os.path.join(mount_path, output_prefix),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )


def build_merge_shards_template(infra_config: InfraConfig):
    if TEMPLATE_NAME not in infra_config.templates:
        raise RuntimeError(f"Infrastructure config has no '{TEMPLATE_NAME}' template")

    template_config = infra_config.templates[TEMPLATE_NAME]

    return script(
        image=CANDIDATES_IMAGE,
        resources=template_resources(template_config),
        volumes=[LYNCEUS_VOLUME],
        image_pull_policy="always",
    )(merge_shards)
