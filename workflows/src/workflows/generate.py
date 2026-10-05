# workflows/src/worksflows/generate_workflow.py

import os
import warnings
from pathlib import Path

import click
from yamlfix import fix_files

from workflows.config import load_config
from workflows.config.infrastructure import InfraConfig
from workflows.config.screen import ScreenConfig
from workflows.registry import WORKFLOW_REGISTRY


@click.command()
@click.option(
    "-w",
    "--workflow",
    "workflows",
    multiple=True,
    required=True,
    type=click.Choice(list(WORKFLOW_REGISTRY.keys())),
    help="Name of the workflow to generate. Can be passed multiple times.",
)
@click.option(
    "-o",
    "--out-dir",
    default=".",
    type=click.Path(exists=True, path_type=Path),
    help="Directory to save the generated YAML files.",
)
@click.option(
    "-s",
    "--screen-config",
    "screen_config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Screen YAML defining what to compute.",
)
@click.option(
    "-i",
    "--infra-config",
    "infra_config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Infrastructure YAML defining how and where to run.",
)
def generate(
    workflows: list[str],
    screen_config_path: Path,
    infra_config_path: Path,
    out_dir: Path,
):

    infra_config = load_config(infra_config_path, InfraConfig)
    screen_config = load_config(screen_config_path, ScreenConfig)

    os.makedirs(out_dir, exist_ok=True)

    generated_files = []

    for wf_name in workflows:
        click.echo(f"Building workflow: {wf_name}...")

        workflow_obj = WORKFLOW_REGISTRY[wf_name](infra_config, screen_config)
        file_path = os.path.join(out_dir, f"{wf_name}.yaml")

        with open(file_path, "w") as f:
            f.write(workflow_obj.to_yaml())

        generated_files.append(file_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fix_files(generated_files)

    for file_path in generated_files:
        click.secho(f"Successfully generated and formatted: {file_path}", fg="green")
