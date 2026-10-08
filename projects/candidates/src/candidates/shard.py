# projects/candidates/src/candidates/shard_candidates.py

import glob
import json
import os
import sys

import click
import duckdb
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()


def _marker_path(output_path: str, input_folder: str) -> str:
    return os.path.join(output_path, f"_SUCCESS_{input_folder}")


def _partition_is_valid(output_path: str, num_shards: int, input_folder: str) -> bool:
    marker_path = _marker_path(output_path, input_folder)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_shards") == num_shards


def _write_success_marker(output_path: str, num_shards: int, input_folder: str) -> None:
    os.makedirs(output_path, exist_ok=True)
    with open(_marker_path(output_path, input_folder), "w") as f:
        json.dump({"num_shards": num_shards}, f)


@click.command("shard_candidates")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input folder",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output folder.",
)
@click.option(
    "--num-shards",
    "num_shards",
    required=True,
    type=click.IntRange(min=1),
    help="Total number of shards to hash-partition rows into.",
)
@click.option(
    "--id-column",
    "id_column",
    default="id",
    show_default=True,
    help="Column used as the hash key for shard assignment.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def shard_candidates(
    input_path: str,
    output_path: str,
    num_shards: int,
    id_column: str,
    num_workers: int,
) -> None:
    click.echo(f"Processing {input_path}...")

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")

    input_folder = os.path.basename(input_path.rstrip("/"))
    source_glob = os.path.join(input_path, "*.parquet")

    if not glob.glob(source_glob):
        raise RuntimeError(
            f"folder={input_folder} resolved to zero parquet files at {source_glob}"
        )

    if _partition_is_valid(output_path, num_shards, input_folder):
        logger.info(
            "Partition already valid, skipping shard creation",
            folder=input_folder,
            num_shards=num_shards,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    logger.info(
        "Hash-partitioning rows into shards",
        source=source_glob,
        id_column=id_column,
        num_shards=num_shards,
        output_path=output_path,
        workers=num_workers,
    )

    os.makedirs(output_path, exist_ok=True)

    conn.sql(
        f"""
        COPY (
            SELECT *, hash({id_column}) % {num_shards} AS shard_id
            FROM read_parquet('{source_glob}')
        )
        TO '{output_path}'
        (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (shard_id), OVERWRITE_OR_IGNORE,
        FILENAME_PATTERN '{input_folder}_{{i}}')
        """
    )

    _write_success_marker(output_path, num_shards, input_folder)

    logger.info(
        "Finished hash-partitioning candidates",
        folder=input_folder,
        num_shards=num_shards,
        output_path=output_path,
    )
    click.echo("Done!")
