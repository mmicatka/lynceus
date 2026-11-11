# libs/lynceus_core/shards/merge_shards.py


import datetime
import glob
import time
from pathlib import Path

import click
import duckdb

from lynceus_core.cli import MemoryLimit
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

DEFAULT_ROW_GROUP_SIZE = 5_000
STAGED_OUTPUT_TRANSFERS = 1

logger = get_lynceus_logger()


PARQUET_PATTERN = "*.parquet"

RUN_TIME_KEY = "run_time"


def _input_manifest(
    input_files: list[str], output_file: str, source_root: Path
) -> Manifest:
    manifest_path = Path(output_file).with_suffix(".manifest.json")
    return Manifest(filepath=manifest_path).set_source_files(input_files, source_root)


def _already_merged(manifest: Manifest, output_file: str) -> bool:
    return Path(output_file).is_file() and manifest.exists_superset()


def _expand_match(match: str) -> list[str]:
    path = Path(match)
    if path.is_dir():
        return [str(file) for file in path.rglob(PARQUET_PATTERN)]
    return [match]


def _find_input_files(input_glob: str) -> list[str]:
    matches = glob.glob(input_glob)
    return sorted({file for match in matches for file in _expand_match(match)})


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("SET arrow_large_buffer_size=true")
    conn.execute("SET preserve_insertion_order=false")
    conn.execute(f"SET memory_limit='{memory_limit}'")

    conn.execute("PRAGMA enable_progress_bar")
    conn.execute("PRAGMA enable_print_progress_bar")
    return conn


def _write_merged_file(
    conn: duckdb.DuckDBPyConnection,
    input_files: list[str],
    output_file: str,
    row_group_size: int,
) -> None:
    conn.execute(
        f"""
        COPY (SELECT * FROM read_parquet(?))
        TO '{output_file}'
        (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {int(row_group_size)})
        """,
        [input_files],
    )


def _merge_via_staged_output(
    input_files: list[str],
    output_file: Path,
    memory_limit: str,
    row_group_size: int,
    scratch_dir: str | None,
) -> None:
    conn = _connect(memory_limit)
    try:
        with staged_output(
            output_file.parent,
            transfers=STAGED_OUTPUT_TRANSFERS,
            scratch_dir=scratch_dir,
        ) as local_output:
            local_file = local_output / output_file.name
            _write_merged_file(conn, input_files, str(local_file), row_group_size)
    finally:
        conn.close()


@click.command("merge_shards")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option(
    "--input",
    "input_glob",
    required=True,
    type=str,
    help="Glob pattern for the parquet files to merge"
    " (e.g., 'path/to/shards/*.parquet').",
)
@click.option(
    "--output",
    "output_file",
    required=True,
    type=str,
    help="Output merged parquet file.",
)
@click.option(
    "--memory-limit",
    "memory_limit",
    default=None,
    type=MemoryLimit(),
    help="DuckDB memory limit, e.g. '48Gi' or '48GB'.",
)
@click.option(
    "--row-group-size",
    default=DEFAULT_ROW_GROUP_SIZE,
    show_default=True,
    type=int,
    help="Rows per output parquet row group; smaller values lower peak memory.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the merged file before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def merge_shards(
    source_root: Path,
    input_glob: str,
    output_file: str,
    memory_limit: str,
    row_group_size: int,
    scratch_dir: str | None,
) -> None:
    click.echo(f"Processing merge for {input_glob}...")

    input_files = _find_input_files(input_glob)
    if not input_files:
        logger.warning("No files found matching glob", input_glob=input_glob)
        click.echo("Done!")
        return

    manifest = _input_manifest(input_files, output_file, source_root)

    try:
        if _already_merged(manifest, output_file):
            logger.info("Valid manifest found.", manifest=manifest.data)
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Merging shard into single file",
        input_glob=input_glob,
        input_files=len(input_files),
        output_file=output_file,
        source_root=str(source_root),
        memory_limit=memory_limit,
        row_group_size=row_group_size,
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    _merge_via_staged_output(
        input_files,
        Path(output_file),
        memory_limit,
        row_group_size,
        scratch_dir,
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished merging shard", input_glob=input_glob, output_file=output_file
    )
    click.echo("Done!")
