# libs/lynceus_core/utils/merge_shards.py

import glob
import json
import os
import shutil
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


def _marker_path(output_dir: str, identifier: str) -> str:
    return os.path.join(output_dir, f"_SUCCESS_{identifier}")


def _merge_is_valid(output_dir: str, identifier: str, num_files: int) -> bool:
    marker_path = _marker_path(output_dir, identifier)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_files") == num_files


def _write_success_marker(output_dir: str, identifier: str, num_files: int) -> None:
    os.makedirs(output_dir, exist_ok=True)
    with open(_marker_path(output_dir, identifier), "w") as f:
        json.dump({"num_files": num_files}, f)


def _find_input_files(input_path: str) -> list[str]:
    return sorted(glob.glob(os.path.join(input_path, "*.parquet")))


def _write_merged_file(conn, input_files: list[str], output_file: str) -> None:
    temp_file = f"{output_file}.tmp"

    conn.execute(
        f"""
        COPY (
            SELECT * FROM read_parquet(?, hive_partitioning=true)
        )
        TO '{temp_file}'
        (FORMAT parquet, COMPRESSION zstd)
        """,
        [input_files],
    )

    if os.path.isdir(output_file):
        shutil.rmtree(output_file)

    os.replace(temp_file, output_file)


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
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def merge_shards(
    input_path: str,
    output_file: str,
    num_workers: int,
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

    identifier = os.path.basename(output_file)

    if _merge_is_valid(output_dir, identifier, len(input_files)):
        logger.info(
            "Merge already valid, skipping generation",
            input_path=input_path,
            output_file=output_file,
            num_files=len(input_files),
        )
        click.echo("Done!")
        return

    logger.info(
        "Merging shard into single file",
        input_path=input_path,
        input_files=len(input_files),
        output_file=output_file,
        workers=num_workers,
    )

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")

    _write_merged_file(conn, input_files, output_file)
    _write_success_marker(output_dir, identifier, len(input_files))

    logger.info(
        "Finished merging shard", input_path=input_path, output_file=output_file
    )
    click.echo("Done!")
