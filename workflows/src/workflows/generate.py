# workflows/src/workflows/generate_workflow.py


from pathlib import Path

import click
import yaml
from pydantic import ValidationError

from workflows.config.common import ConfigError
from workflows.config.core import WorkflowConfigs
from workflows.registry import WORKFLOW_REGISTRY

CONFIG_ERRORS = (ConfigError, ValidationError, yaml.YAMLError)


def _load_configs(
    candidates_path: Path,
    templates_path: Path,
    screen_path: Path,
) -> WorkflowConfigs:
    try:
        return WorkflowConfigs.load(
            candidates_path=candidates_path,
            templates_path=templates_path,
            screen_path=screen_path,
        )
    except CONFIG_ERRORS as error:
        raise click.ClickException(str(error)) from error


def _render_workflows(
    names: tuple[str, ...],
    configs: WorkflowConfigs,
) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name in names:
        click.echo(f"Building workflow: {name}...")
        rendered[name] = WORKFLOW_REGISTRY[name](configs).to_yaml()
    return rendered


def _write_workflows(rendered: dict[str, str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, content in rendered.items():
        path = out_dir / f"{name}.yaml"
        path.write_text(content)
        paths.append(path)
    return paths


@click.command()
@click.option(
    "-w",
    "--workflow",
    "workflows",
    multiple=True,
    required=True,
    type=click.Choice(list(WORKFLOW_REGISTRY)),
    help="Name of the workflow to generate. Can be passed multiple times.",
)
@click.option(
    "-o",
    "--out-dir",
    default=".",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to save the generated YAML files. Created if missing.",
)
@click.option(
    "-c",
    "--candidates-config",
    "candidates_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Candidates YAML defining candidate storage and samples.",
)
@click.option(
    "-t",
    "--templates-config",
    "templates_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Templates YAML defining how and where each template runs.",
)
@click.option(
    "-s",
    "--screen-config",
    "screen_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Screen YAML defining what to compute.",
)
def generate(
    workflows: tuple[str, ...],
    out_dir: Path,
    candidates_path: Path,
    templates_path: Path,
    screen_path: Path,
) -> None:
    configs = _load_configs(candidates_path, templates_path, screen_path)
    rendered = _render_workflows(workflows, configs)
    for path in _write_workflows(rendered, out_dir):
        click.secho(f"Generated: {path}", fg="green")
