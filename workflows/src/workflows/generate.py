# workflows/src/worksflows/generate_workflow.py

import os
import warnings

import click
from yamlfix import fix_files

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
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    help="Directory to save the generated YAML files.",
)
def generate(workflows, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    generated_files = []

    for wf_name in workflows:
        click.echo(f"Building workflow: {wf_name}...")

        workflow_obj = WORKFLOW_REGISTRY[wf_name]()
        file_path = os.path.join(out_dir, f"{wf_name}.yaml")

        with open(file_path, "w") as f:
            f.write(workflow_obj.to_yaml())

        generated_files.append(file_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fix_files(generated_files)

    for file_path in generated_files:
        click.secho(f"Successfully generated and formatted: {file_path}", fg="green")
