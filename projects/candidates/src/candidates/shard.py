# projects/candidates/src/candidates/shard.py

import json
import os
from pathlib import Path

import click
import duckdb
from lynceus_core.cli import NumWorkers
from lynceus_core.io import plan_batches, staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log

logger = get_lynceus_logger()


def _read_marker(path: Path) -> dict | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError:
        return None


def _write_marker(output_path: Path, payload: dict) -> None:
    with open(output_path, "w") as f:
        json.dump(payload, f)


def _partition_marker_path(output_path: Path, input_folder: str) -> Path:
    return output_path / f"_SUCCESS_{input_folder}"


def _partition_marker_payload(num_shards: int) -> dict:
    return {"num_shards": num_shards}


def _partition_is_valid(output_path: Path, num_shards: int, input_folder: str) -> bool:
    marker = _read_marker(_partition_marker_path(output_path, input_folder))
    return marker == _partition_marker_payload(num_shards)


def _batch_prefix(input_folder: str, batch_index: int) -> str:
    return f"{input_folder}_b{batch_index}"


def _batch_marker_path(output_path: Path, input_folder: str, batch_index: int) -> Path:
    return output_path / f"_SUCCESS_{_batch_prefix(input_folder, batch_index)}"


def _batch_marker_payload(num_shards: int, batch: list[Path]) -> dict:
    return {
        "num_shards": num_shards,
        "files": [{"name": path.name, "size": path.stat().st_size} for path in batch],
    }


def _batch_is_valid(
    output_path: Path,
    input_folder: str,
    batch_index: int,
    num_shards: int,
    batch: list[Path],
) -> bool:
    marker = _read_marker(_batch_marker_path(output_path, input_folder, batch_index))
    return marker == _batch_marker_payload(num_shards, batch)


def _purge_batch_outputs(output_path: Path, prefix: str) -> None:
    for stale in output_path.glob(f"shard_id=*/{prefix}_*"):
        stale.unlink()


def _configure_connection(
    conn: duckdb.DuckDBPyConnection,
    num_workers: int,
    num_shards: int,
    memory_limit: str | None,
) -> None:
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")
    conn.execute(f"SET partitioned_write_max_open_files = {num_shards}")
    if memory_limit:
        conn.execute("SET memory_limit = ?", [memory_limit])


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


def _process_batch(
    conn: duckdb.DuckDBPyConnection,
    batch: list[Path],
    batch_index: int,
    output_path: Path,
    input_folder: str,
    id_column: str,
    num_shards: int,
    transfers: int,
    scratch_dir: str | None,
) -> None:
    prefix = _batch_prefix(input_folder, batch_index)
    _purge_batch_outputs(output_path, prefix)

    with staged_io(batch, output_path, transfers, scratch_dir) as (
        local_input,
        local_output,
    ):
        _shard_batch(conn, local_input, local_output, id_column, num_shards, prefix)

    _write_marker(
        _batch_marker_path(output_path, input_folder, batch_index),
        _batch_marker_payload(num_shards, batch),
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
@click.option(
    "--memory-limit",
    "memory_limit",
    default=None,
    type=str,
    help="DuckDB memory limit, e.g. '48GB'. Defaults to DuckDB's own default.",
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
    memory_limit: str | None,
) -> None:
    click.echo(f"Processing {input_path}...")

    output = Path(output_path)
    input_folder = os.path.basename(input_path.rstrip("/"))
    input_files = sorted(Path(input_path).glob("*.parquet"))

    if not input_files:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero parquet files at {input_path}"
        )

    if _partition_is_valid(output, num_shards, input_folder):
        logger.info(
            "Partition already valid, skipping shard creation",
            folder=input_folder,
            num_shards=num_shards,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    conn = duckdb.connect()
    _configure_connection(conn, num_workers, num_shards, memory_limit)

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
        memory_limit=memory_limit,
    )

    output.mkdir(parents=True, exist_ok=True)

    for batch_index, batch in enumerate(batches):
        if _batch_is_valid(output, input_folder, batch_index, num_shards, batch):
            logger.info(
                "Batch already valid, skipping",
                folder=input_folder,
                batch=batch_index,
            )
            continue

        _process_batch(
            conn,
            batch,
            batch_index,
            output,
            input_folder,
            id_column,
            num_shards,
            transfers,
            scratch_dir,
        )
        logger.info(
            "Flushed batch",
            folder=input_folder,
            batch=batch_index,
            files=len(batch),
        )

    _write_marker(
        _partition_marker_path(output, input_folder),
        _partition_marker_payload(num_shards),
    )

    logger.info(
        "Finished hash-partitioning candidates",
        folder=input_folder,
        num_shards=num_shards,
        output_path=output_path,
    )
    click.echo("Done!")
