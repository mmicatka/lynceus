# workflows/src/workflows/templates/candidates/generate_subset_manifest.py

from hera.workflows import script

from workflows.config import InfraConfig
from workflows.config.images import CANDIDATES_IMAGE
from workflows.resources import LYNCEUS_VOLUME
from workflows.templates.common import template_resources

TEMPLATE_NAME = "generate_subset_manifest"


def generate_subset_manifest(
    source_dir: str,
    target_total: int,
    min_per_source: int,
    output: str,
):
    import subprocess

    subprocess.run(
        [
            "generate-candidates-subset-manifest",
            "--source-dir",
            str(source_dir),
            "--target-total",
            str(target_total),
            "--min-per-source",
            str(min_per_source),
            "--output",
            str(output),
        ],
        check=True,
    )


def build_generate_subset_manifest_template(infra_config: InfraConfig):
    if TEMPLATE_NAME not in infra_config.templates:
        raise RuntimeError(f"Infrastructure config has no '{TEMPLATE_NAME}' template")

    template_config = infra_config.templates[TEMPLATE_NAME]

    return script(
        image=CANDIDATES_IMAGE,
        resources=template_resources(template_config),
        volumes=[LYNCEUS_VOLUME],
        image_pull_policy="always",
    )(generate_subset_manifest)
