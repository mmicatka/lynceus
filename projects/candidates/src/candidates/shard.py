# projects/candidates/src/candidates/shard_candidates.py

# projects/candidates/src/candidates/shard_candidates.py

import json
import os
import sys
from pathlib import Path

import click
import duckdb
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.io import plan_batches, staged_io
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


def _batch_marker_path(output_path: str, input_folder: str, batch_index: int) -> str:
    return os.path.join(output_path, f"_SUCCESS_{input_folder}_batch_{batch_index}")


def _batch_marker_payload(num_shards: int, batch: list[Path]) -> dict:
    return {"num_shards": num_shards, "files": [path.name for path in batch]}


def _batch_is_valid(
    output_path: str,
    input_folder: str,
    batch_index: int,
    num_shards: int,
    batch: list[Path],
) -> bool:
    marker_path = _batch_marker_path(output_path, input_folder, batch_index)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        return json.load(f) == _batch_marker_payload(num_shards, batch)


def _write_batch_marker(
    output_path: str,
    input_folder: str,
    batch_index: int,
    num_shards: int,
    batch: list[Path],
) -> None:
    with open(_batch_marker_path(output_path, input_folder, batch_index), "w") as f:
        json.dump(_batch_marker_payload(num_shards, batch), f)


def _shard_batch(
    conn: duckdb.DuckDBPyConnection,
    local_input: Path,
    local_output: Path,
    id_column: str,
    num_shards: int,
    filename_prefix: str,
) -> None:
    conn.sql(
        f"""
        COPY (
            SELECT *, hash({id_column}) % {num_shards} AS shard_id
            FROM read_parquet('{local_input}/*.parquet')
        )
        TO '{local_output}'
        (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (shard_id),
        OVERWRITE_OR_IGNORE,
        FILENAME_PATTERN '{filename_prefix}_{{i}}')
        """
    )


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
@click.option(
    "--transfers",
    default=4,
    type=click.IntRange(min=1),
    show_default=True,
    help="Concurrent file copies between the mount and local scratch.",
)
@click.option(
    "--scratch-dir",
    "scratch_dir",
    default=None,
    type=click.Path(file_okay=False),
    help="Local scratch directory for staging. Defaults to the system temp dir.",
)
@click.option(
    "--max-batch-gib",
    "max_batch_gib",
    default=50,
    type=click.IntRange(min=1),
    show_default=True,
    help="Maximum input size per batch. Peak scratch is roughly twice this.",
)
@wide_log(logger)
def shard_candidates(
    input_path: str,
    output_path: str,
    num_shards: int,
    id_column: str,
    num_workers: int,
    transfers: int,
    scratch_dir: str | None,
    max_batch_gib: int,
) -> None:
    click.echo(f"Processing {input_path}...")

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")

    input_folder = os.path.basename(input_path.rstrip("/"))
    input_files = sorted(Path(input_path).glob("*.parquet"))

    if not input_files:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero parquet files at {input_path}"
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

    batches = plan_batches(input_files, max_batch_gib * 1024**3)

    logger.info(
        "Hash-partitioning rows into shards",
        source=input_path,
        id_column=id_column,
        num_shards=num_shards,
        output_path=output_path,
        workers=num_workers,
        transfers=transfers,
        batches=len(batches),
    )

    os.makedirs(output_path, exist_ok=True)

    for batch_index, batch in enumerate(batches):
        if _batch_is_valid(output_path, input_folder, batch_index, num_shards, batch):
            logger.info(
                "Batch already valid, skipping",
                folder=input_folder,
                batch=batch_index,
            )
            continue

        with staged_io(batch, Path(output_path), transfers, scratch_dir) as (
            local_input,
            local_output,
        ):
            _shard_batch(
                conn,
                local_input,
                local_output,
                id_column,
                num_shards,
                f"{input_folder}_b{batch_index}",
            )

        _write_batch_marker(output_path, input_folder, batch_index, num_shards, batch)
        logger.info(
            "Flushed batch",
            folder=input_folder,
            batch=batch_index,
            files=len(batch),
        )

    _write_success_marker(output_path, num_shards, input_folder)

    logger.info(
        "Finished hash-partitioning candidates",
        folder=input_folder,
        num_shards=num_shards,
        output_path=output_path,
    )
    click.echo("Done!")
