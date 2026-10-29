# libs/lynceus_core/utils/merge_shards.py

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


def _find_input_files(input_glob: str) -> list[str]:
    return sorted(glob.glob(input_glob))


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("SET arrow_large_buffer_size=true")
    conn.execute("SET preserve_insertion_order=false")
    conn.execute(f"SET memory_limit='{memory_limit}'")
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

    manifest_path = str(Path(output_file).with_suffix(".manifest.json"))
    manifest_data = {
        "input_files": input_files,
    }

    manifest = Manifest(data=manifest_data, filepath=manifest_path)

    try:
        if manifest.exists_superset():
            logger.info(
                "Valid manifest found.",
                manifest=manifest.data,
            )
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Merging shard into single file",
        input_glob=input_glob,
        input_files=len(input_files),
        output_file=output_file,
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
    manifest.data = manifest_data
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished merging shard", input_glob=input_glob, output_file=output_file
    )
    click.echo("Done!")
