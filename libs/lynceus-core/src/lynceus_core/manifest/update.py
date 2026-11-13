# libs/lynceus-core/src/lynceus_core/manifest/update.py


import json
from pathlib import Path
from typing import Any

import click

from lynceus_core.manifest.common import Manifest


def _parse_fields(
    ctx: click.Context, param: click.Parameter, value: str
) -> dict[str, Any]:
    try:
        fields = json.loads(value)
    except json.JSONDecodeError as error:
        raise click.BadParameter(f"Invalid JSON: {error}") from error
    if not isinstance(fields, dict):
        raise click.BadParameter("Expected a JSON object.")
    return fields


@click.command("update_manifest")
@click.option(
    "--source",
    "source_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Manifest or plan JSON to load as the starting point.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Manifest file to write atomically.",
)
@click.option(
    "--set",
    "fields",
    required=True,
    callback=_parse_fields,
    help="JSON object of top-level keys to set.",
)
def update_manifest(
    source_path: Path, output_path: Path, fields: dict[str, Any]
) -> None:
    manifest = Manifest(filepath=source_path).load()
    manifest.data.update(fields)
    manifest.filepath = output_path
    manifest.save()
    click.echo(f"Wrote {output_path} with keys {sorted(fields)}")
