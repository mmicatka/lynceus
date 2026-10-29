# projects/candidates/src/candidates/shard.py

import datetime
import os
import time
from pathlib import Path

import click
import duckdb
from lynceus_core.cli import MemoryLimit, NumWorkers
from lynceus_core.io import plan_batches, staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest import Manifest

logger = get_lynceus_logger()


def _batch_prefix(input_folder: str, batch_index: int) -> str:
    return f"{input_folder}_b{batch_index}"


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
    local_input: list[Path],
    local_output: Path,
    id_column: str,
    num_shards: int,
    filename_prefix: str,
) -> None:
    input_files = ", ".join(f"'{p}'" for p in local_input)

    conn.sql(
        f"""
        COPY (
            SELECT *, hash({id_column}) % {num_shards} AS shard_id
            FROM read_parquet([{input_files}])
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
    default="6GB",
    type=MemoryLimit(),
    help="DuckDB memory limit, e.g. '48Gi' or '48GB'.",
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

    memory_limit = "6GB"
    num_workers = 1

    output = Path(output_path)
    input_folder = os.path.basename(input_path.rstrip("/"))
    input_files = sorted(Path(input_path).glob("*.parquet"))

    if not input_files:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero parquet files at {input_path}"
        )

    manifest_data = {
        "input_path": input_path,
        "output_path": output_path,
        "num_shards": num_shards,
        "id_column": id_column,
        "max_batch_gib": max_batch_gib,
    }

    manifest_path = f"{output_path.rstrip('/')}.{Path(input_path).name}.manifest.json"
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

    start_time = time.perf_counter()

    for batch_index, batch in enumerate(batches):
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
            "Processed batch",
            folder=input_folder,
            batch=batch_index,
            files=len(batch),
        )

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished hash-partitioning candidates",
        folder=input_folder,
        num_shards=num_shards,
        output_path=output_path,
    )
    click.echo("Done!")


if __name__ == "__main__":
    shard_candidates()
