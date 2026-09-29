# modules/local/rebalance_candidates/src/rebalance_candidates/shard/shard.py

import json
import logging

import click
from lynceus_utils.cli import NumWorkers
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _marker_path(output_path: str, input_name: str) -> str:
    return f"{output_path.rstrip('/')}/_SUCCESS_{input_name}"


def _partition_is_valid(
    filesystem, output_path: str, num_shards: int, input_name: str
) -> bool:
    marker_path = _marker_path(output_path, input_name)
    if not filesystem.exists(marker_path):
        return False
    with filesystem.open(marker_path, "r") as f:
        return json.load(f).get("num_shards") == num_shards


def _write_success_marker(
    filesystem, output_path: str, num_shards: int, input_name: str
) -> None:
    with filesystem.open(_marker_path(output_path, input_name), "w") as f:
        json.dump({"num_shards": num_shards}, f)


def _is_explicit_parquet_source(path: str) -> bool:
    basename = path.rstrip("/").split("/")[-1]
    return basename.endswith(".parquet") or "*" in basename


def _get_input_name(input_path: str) -> str:
    clean_path = input_path.rstrip("/")
    basename = clean_path.split("/")[-1]
    if _is_explicit_parquet_source(clean_path):
        parts = clean_path.split("/")
        if len(parts) > 1:
            return parts[-2]
        return basename.replace(".parquet", "").replace("*", "all")
    return basename


def _resolve_parquet_source(filesystem, input_path: str) -> str:
    source = (
        input_path
        if _is_explicit_parquet_source(input_path)
        else f"{input_path.rstrip('/')}/*.parquet"
    )
    if not filesystem.glob(source):
        raise RuntimeError(f"no parquet files match {source}")
    return source


def _resolve_path(use_blob_storage: bool, bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key.lstrip('/')}" if use_blob_storage else key


@click.command()
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
    "--use-blob-storage",
    is_flag=True,
    help="Read source and write output via blob storage.",
)
@click.option("--bucket", type=str, help="S3-compatible bucket name.")
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def shard_candidates(
    input_path: str,
    output_path: str,
    num_shards: int,
    id_column: str,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
) -> None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    conn = get_connection(blob_storage_settings, threads=num_workers)
    filesystem = get_filesystem(blob_storage_settings)

    resolved_input = _resolve_path(use_blob_storage, bucket, input_path)
    resolved_output = _resolve_path(use_blob_storage, bucket, output_path)

    input_name = _get_input_name(input_path)

    if _partition_is_valid(filesystem, resolved_output, num_shards, input_name):
        logger.info(
            "input=%s already partitioned into %d shards at %s, skipping",
            resolved_input,
            num_shards,
            resolved_output,
        )
        return

    resolved_source = _resolve_parquet_source(filesystem, resolved_input)

    logger.info(
        "input=%s hash-partitioning by %s into %d shards at %s",
        resolved_source,
        id_column,
        num_shards,
        resolved_output,
    )

    conn.sql(
        f"""
        COPY (
            SELECT *, hash({id_column}) % {num_shards} AS shard_id
            FROM read_parquet('{resolved_source}')
        )
        TO '{resolved_output}'
        (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (shard_id), OVERWRITE_OR_IGNORE,
        FILENAME_PATTERN '{input_name}_{{i}}')
        """
    )

    _write_success_marker(filesystem, resolved_output, num_shards, input_name)

    logger.info(
        "input=%s finished hash-partitioning into %d shards at %s",
        resolved_input,
        num_shards,
        resolved_output,
    )
