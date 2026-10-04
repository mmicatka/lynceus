# workflows/src/worksflows/generate_workflow.py

import os

import click

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
    """Generate Argo YAML manifests from Hera Python definitions."""
    os.makedirs(out_dir, exist_ok=True)

    for wf_name in workflows:
        click.echo(f"Building workflow: {wf_name}...")

        workflow_obj = WORKFLOW_REGISTRY[wf_name]()

        file_path = os.path.join(out_dir, f"{wf_name}.yaml")

        with open(file_path, "w") as f:
            f.write(
                workflow_obj.to_yaml(
                    explicit_start=True,
                )
            )

        click.secho(f"Successfully generated: {file_path}", fg="green")
