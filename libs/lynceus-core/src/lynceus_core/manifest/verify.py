# libs/lynceus-core/src/lynceus_core/manifest/verify.py


import json
import os

import click

from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

TRUE = "true"
FALSE = "false"

logger = get_lynceus_logger()


def _parse_expected(_ctx: click.Context, _param: click.Parameter, value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"invalid JSON: {e}")
    if not isinstance(parsed, dict):
        raise click.BadParameter("must be a JSON object")
    return parsed


def _manifest_matches(manifest_path: str, expected: dict) -> bool:
    disk_manifest = Manifest(filepath=manifest_path)
    if not disk_manifest.exists():
        return False
    try:
        disk_manifest.load()
    except Exception as e:
        logger.warning("Failed to load existing manifest", error=str(e))
        return False
    return Manifest(data=expected) <= disk_manifest


def _write_result(result_file: str, matches: bool) -> None:
    result_dir = os.path.dirname(result_file)
    if result_dir:
        os.makedirs(result_dir, exist_ok=True)
    with open(result_file, "w") as handle:
        handle.write(TRUE if matches else FALSE)


@click.command("check_manifest")
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=str,
    help="Path to the manifest file to check.",
)
@click.option(
    "--expect",
    "expected",
    default="{}",
    show_default=True,
    callback=_parse_expected,
    help="JSON object of key/values the manifest must contain.",
)
@click.option(
    "--result-file",
    default="/tmp/manifest_matches.txt",
    show_default=True,
    type=str,
    help="File the true/false result is written to (read as an Argo output parameter).",
)
@wide_log(logger)
def verify_manifest(manifest_path: str, expected: dict, result_file: str) -> None:
    click.echo(f"Checking manifest {manifest_path}...")

    matches = _manifest_matches(manifest_path, expected)
    _write_result(result_file, matches)

    logger.info(
        "Checked manifest",
        manifest_path=manifest_path,
        expected=expected,
        manifest_matches=matches,
    )
    click.echo("Done!")
