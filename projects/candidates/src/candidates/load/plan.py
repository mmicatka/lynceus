# projects/candidates/src/candidates/load/plan.py


import json
from pathlib import Path
from typing import Any

import click
from lynceus_core.manifest.common import (
    FINGERPRINT_KEY,
    PATH_FIELD,
    SOURCE_FILES_KEY,
    Manifest,
)
from lynceus_core.manifest.fingerprint import SIZE_FIELD

BYTES_PER_GIB = 1024**3
SourceEntry = dict[str, Any]


def scan_files(source_root: Path, source_glob: str) -> list[SourceEntry]:
    paths = (path for path in source_root.glob(source_glob) if path.is_file())
    return Manifest.describe_files(paths, source_root)


def _entry_size(entry: SourceEntry) -> int:
    return entry[FINGERPRINT_KEY][SIZE_FIELD]


def _pack_batches(files: list[SourceEntry], max_batch_bytes: float) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_bytes = 0

    for entry in files:
        size = _entry_size(entry)
        if current and current_bytes + size > max_batch_bytes:
            batches.append(current)
            current, current_bytes = [], 0
        current.append(entry[PATH_FIELD])
        current_bytes += size

    if current:
        batches.append(current)
    return batches


def _write_plan(batches: list[list[str]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps({"batches": batches}, separators=(",", ":")))


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
    default="**/*",
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
@click.option(
    "--max-batch-gib",
    default=10.0,
    show_default=True,
    type=click.FloatRange(min=0, min_open=True),
    help="Maximum total input size per batch. A larger single file gets its own batch.",
)
def plan_load_candidates(
    source_root: Path,
    source_glob: str,
    output_file: Path,
    persist_file: Path,
    max_batch_gib: float,
) -> None:
    files = scan_files(source_root, source_glob)
    if not files:
        raise click.ClickException(
            f"No files matched {source_glob!r} under {source_root}"
        )

    batches = _pack_batches(files, max_batch_gib * BYTES_PER_GIB)
    _persist_source_files(files, persist_file)
    _write_plan(batches, output_file)
    click.echo(f"Planned {len(files)} files into {len(batches)} batches")
