# libs/lynceus-core/src/lynceus_core/plan.py


import json
from pathlib import Path
from typing import Any

import click

from lynceus_core.manifest.common import (
    PATH_FIELD,
    SOURCE_FILES_KEY,
    Manifest,
)

SourceEntry = dict[str, Any]


def _scan_files(source_root: Path, source_glob: str) -> list[SourceEntry]:
    paths = (path for path in source_root.glob(source_glob) if path.is_file())
    return Manifest.describe_files(paths, source_root)


def _extract_sources(files: list[SourceEntry]) -> list[str]:
    return [Path(entry[PATH_FIELD]).name for entry in files]


def _write_plan(sources: list[str], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps({"sources": sources}, separators=(",", ":")))


def _persist_source_files(files: list[SourceEntry], persist_file: Path) -> None:
    Manifest(data={SOURCE_FILES_KEY: files}, filepath=persist_file).save()


@click.command()
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to scan for files.",
)
@click.option(
    "--source-glob",
    default="*",
    show_default=True,
    help="Glob, relative to --source-root, selecting the files.",
)
@click.option(
    "--output-file",
    default="/tmp/manifest.json",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="File the plan JSON is written to (read as an Argo output parameter).",
)
@click.option(
    "--persist-file",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="File the planned source files and their fingerprints are persisted to.",
)
def generate_plan(
    source_root: Path,
    source_glob: str,
    output_file: Path,
    persist_file: Path,
) -> None:
    files = _scan_files(source_root, source_glob)
    if not files:
        raise click.ClickException(
            f"No files matched {source_glob!r} under {source_root}"
        )

    sources = _extract_sources(files)
    _persist_source_files(files, persist_file)
    _write_plan(sources, output_file)
    click.echo(f"Planned {len(sources)} files for preprocessing")
