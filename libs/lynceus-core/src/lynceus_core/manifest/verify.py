# libs/lynceus-core/src/lynceus_core/manifest/verify.py

import json
import os
from pathlib import Path
from typing import Optional

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


def _write_result(result_file: str, matches: bool) -> None:
    result_dir = os.path.dirname(result_file)
    if result_dir:
        os.makedirs(result_dir, exist_ok=True)
    with open(result_file, "w") as handle:
        handle.write(TRUE if matches else FALSE)


def _manifest_matches(
    manifest_path: str,
    expected: dict,
    source_root: Optional[str],
    source_glob: str,
) -> bool:
    manifest = Manifest(data=expected, filepath=manifest_path)
    if not manifest.exists_superset():
        return False
    if source_root is None:
        return True

    manifest.set_source_files(Path(source_root).glob(source_glob), root=source_root)
    return manifest.exists_superset()


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
    "--source-root",
    default=None,
    type=str,
    help="Directory the manifest's relative source file paths resolve against. "
    "When set, source files are re-hashed and compared to the manifest.",
)
@click.option(
    "--source-glob",
    default="*",
    show_default=True,
    type=str,
    help="Glob, relative to --source-root, selecting the expected source files.",
)
@click.option(
    "--result-file",
    default="/tmp/manifest_matches.txt",
    show_default=True,
    type=str,
    help="File the true/false result is written to.",
)
@wide_log(logger)
def verify_manifest(
    manifest_path: str,
    expected: dict,
    source_root: Optional[str],
    source_glob: str,
    result_file: str,
) -> None:
    click.echo(f"Checking manifest {manifest_path}...")

    matches = False

    try:
        matches = _manifest_matches(manifest_path, expected, source_root, source_glob)
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    _write_result(result_file, matches)

    logger.info(
        "Checked manifest",
        manifest_path=manifest_path,
        expected=expected,
        source_root=source_root,
        source_glob=source_glob,
        manifest_matches=matches,
    )
    click.echo("Done!")
