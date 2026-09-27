# modules/local/rebalance_candidates/src/rebalance_candidates/shard/concat_shards.py

import logging

import click
from lynceus_utils.cli import NumWorkers
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


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
def concat_shards(
    input_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
) -> None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    conn = get_connection(blob_storage_settings, threads=num_workers)
    filesystem = get_filesystem(blob_storage_settings)

    resolved_input = _resolve_path(use_blob_storage, bucket, input_path)
    resolved_output = _resolve_path(use_blob_storage, bucket, output_path)

    search_pattern = f"{resolved_input.rstrip('/')}/*.parquet"
    raw_files = filesystem.glob(search_pattern)

    if not raw_files:
        logger.error("No parquet files found in %s", input_path)
        return

    files: list[str] = [str(f) for f in raw_files]
    resolved_files = [
        _resolve_path(use_blob_storage, bucket, f.replace(f"s3://{bucket}/", ""))
        for f in files
    ]
    resolved_files.sort()

    logger.info(
        "Found %d files in %s. Concatenating in deterministic order...",
        len(resolved_files),
        input_path,
    )
    for f in resolved_files:
        logger.info(" - %s", f)

    file_list_sql = "[" + ", ".join([f"'{f}'" for f in resolved_files]) + "]"

    conn.sql(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({file_list_sql})
        )
        TO '{resolved_output}'
        (FORMAT parquet, COMPRESSION zstd, OVERWRITE_OR_IGNORE)
        """
    )

    logger.info("Successfully concatenated files into %s", resolved_output)
