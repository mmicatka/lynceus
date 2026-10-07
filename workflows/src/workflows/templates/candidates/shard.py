# workflows/src/workflows/templates/candidates/shard.py

from hera.workflows import script

from workflows.config import InfraConfig
from workflows.config.images import CANDIDATES_IMAGE
from workflows.resources import LYNCEUS_VOLUME
from workflows.templates.resources import template_resources

TEMPLATE_NAME = "shard_candidates"


def shard_candidates(
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    num_shards: int,
    id_column: str = "id",
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "shard-candidates",
            "--input",
            os.path.join(mount_path, input_prefix),
            "--output",
            os.path.join(mount_path, output_prefix),
            "--num-shards",
            str(num_shards),
            "--id-column",
            id_column,
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )


def build_shard_candidates_template(infra_config: InfraConfig):
    if TEMPLATE_NAME not in infra_config.templates:
        raise RuntimeError(f"Infrastructure config has no '{TEMPLATE_NAME}' template")

    template_config = infra_config.templates[TEMPLATE_NAME]

    return script(
        image=CANDIDATES_IMAGE,
        resources=template_resources(template_config),
        volumes=[LYNCEUS_VOLUME],
        image_pull_policy="always",
    )(shard_candidates)
