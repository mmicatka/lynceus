# modules/local/rebalance_candidates/src/rebalance_candidates/shard/concat_shards.py

import json
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


def _with_scheme(use_blob_storage: bool, path: str) -> str:
    if use_blob_storage and not path.startswith("s3://"):
        return f"s3://{path}"
    return path


def _list_inputs(
    filesystem, use_blob_storage: bool, input_pattern: str, output_file: str
) -> list[str]:
    matches = sorted(
        path
        for path in (
            _with_scheme(use_blob_storage, str(raw))
            for raw in filesystem.glob(input_pattern)
        )
        if path != output_file
    )
    if not matches:
        raise RuntimeError(f"no parquet files match {input_pattern}")
    return matches


def _manifest_path(output_file: str) -> str:
    return f"{output_file}.inputs.json"


def _read_manifest(filesystem, manifest_path: str) -> list[str] | None:
    if not filesystem.exists(manifest_path):
        return None
    with filesystem.open(manifest_path, "r") as f:
        return json.load(f)["inputs"]


def _write_manifest(filesystem, manifest_path: str, inputs: list[str]) -> None:
    with filesystem.open(manifest_path, "w") as f:
        json.dump({"inputs": inputs}, f)


def _output_is_valid(filesystem, output_file: str, inputs: list[str]) -> bool:
    return filesystem.exists(output_file) and (
        _read_manifest(filesystem, _manifest_path(output_file)) == inputs
    )


def _concat(conn, inputs: list[str], output_file: str) -> None:
    file_list_sql = "[" + ", ".join(f"'{path}'" for path in inputs) + "]"
    conn.sql(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({file_list_sql}, hive_partitioning = false)
        )
        TO '{output_file}'
        (FORMAT parquet, COMPRESSION zstd)
        """
    )


@click.command()
@click.option(
    "--input",
    "input_pattern",
    required=True,
    type=str,
    help="Glob matching the parquet files to concatenate.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output parquet file.",
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
    input_pattern: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
) -> None:
    if use_blob_storage and not bucket:
        raise click.UsageError("--bucket is required with --use-blob-storage")

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    conn = get_connection(blob_storage_settings, threads=num_workers)
    filesystem = get_filesystem(blob_storage_settings)

    resolved_input = _resolve_path(use_blob_storage, bucket, input_pattern)
    resolved_output = _resolve_path(use_blob_storage, bucket, output_path)

    inputs = _list_inputs(filesystem, use_blob_storage, resolved_input, resolved_output)

    if _output_is_valid(filesystem, resolved_output, inputs):
        logger.info(
            "%s already concatenated from %d inputs, skipping",
            resolved_output,
            len(inputs),
        )
        return

    logger.info("concatenating %d files into %s", len(inputs), resolved_output)
    _concat(conn, inputs, resolved_output)
    _write_manifest(filesystem, _manifest_path(resolved_output), inputs)
    logger.info("finished concatenating into %s", resolved_output)
