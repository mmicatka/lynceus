# libs/lynceus_core/utils/merge_shards.py

import datetime
import glob
import os
import time

import click
import duckdb

from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import MANIFEST_SUFFIX, Manifest

DEFAULT_ROW_GROUP_SIZE = 5_000
PARQUET_GLOB = "*.parquet"

logger = get_lynceus_logger()


def _find_input_files(input_path: str) -> list[str]:
    return sorted(glob.glob(os.path.join(input_path, PARQUET_GLOB)))


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


@click.command("merge_shards")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Shard folder (e.g. .../shard_id=3) containing the parquet files to merge.",
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
    type=str,
    default="4GB",
    help="DuckDB memory limit (e.g. 4GB).",
)
@click.option(
    "--row-group-size",
    default=DEFAULT_ROW_GROUP_SIZE,
    show_default=True,
    type=int,
    help="Rows per output parquet row group; smaller values lower peak memory.",
)
@wide_log(logger)
def merge_shards(
    input_path: str,
    output_file: str,
    memory_limit: str,
    row_group_size: int,
) -> None:
    click.echo(f"Processing merge for {input_path}...")

    input_files = _find_input_files(input_path)
    if not input_files:
        logger.warning("No parquet files found for shard", input_path=input_path)
        click.echo("Done!")
        return

    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    manifest_path = f"{output_file}.{MANIFEST_SUFFIX}"
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
        input_path=input_path,
        input_files=len(input_files),
        output_file=output_file,
        memory_limit=memory_limit,
        row_group_size=row_group_size,
    )

    start_time = time.perf_counter()

    conn = _connect(memory_limit)
    try:
        _write_merged_file(conn, input_files, output_file, row_group_size)
    finally:
        conn.close()

    elapsed_time = time.perf_counter() - start_time
    manifest.data = manifest_data
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished merging shard", input_path=input_path, output_file=output_file
    )
    click.echo("Done!")
