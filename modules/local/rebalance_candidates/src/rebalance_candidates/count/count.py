# modules/local/rebalance_candidates/src/rebalance_candidates/count_candidates.py

import json
import logging

import click
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _resolve_path(path: str, use_blob_storage: bool, bucket: str) -> str:
    return f"s3://{bucket}/{path.lstrip('/')}" if use_blob_storage else path


def _read_json(path: str, use_blob_storage: bool, bucket: str) -> dict | None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = _resolve_path(path, use_blob_storage, bucket)

    if not fs.exists(resolved_path):
        return None

    with fs.open(resolved_path, "r") as f:
        return json.load(f)


def _write_json(
    output_path: str, payload: dict, use_blob_storage: bool, bucket: str
) -> None:
    content = json.dumps(payload)

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = _resolve_path(output_path, use_blob_storage, bucket)

    with fs.open(resolved_path, "w") as f:
        f.write(content)

    logger.info("Wrote candidate count to %s", resolved_path)


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
    help="Output path for the candidate count JSON.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read source and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def count_candidates(
    input_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    folder = input_path.rstrip("/").split("/")[-1]

    existing = _read_json(output_path, use_blob_storage, bucket)
    if (
        existing is not None
        and existing.get("folder") == folder
        and existing.get("count", 0) > 0
    ):
        logger.info(
            "folder=%s already counted at %s (count=%d), skipping",
            folder,
            output_path,
            existing["count"],
        )
        return

    source_glob = f"{input_path.rstrip('/')}/*.smi.gz"

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        source_glob = f"s3://{bucket}/{source_glob.lstrip('/')}"
    else:
        conn = get_connection()

    logger.info("Counting folder=%s from %s", folder, source_glob)

    rel = conn.read_csv(
        source_glob,
        delimiter="\t",
        header=False,
        columns={"smiles": "VARCHAR", "id": "VARCHAR"},
    )
    row_count_result = rel.count("*").fetchone()
    if row_count_result is None:
        raise RuntimeError(f"Count query returned no result for folder={folder}")

    row_count = row_count_result[0]
    if row_count == 0:
        raise RuntimeError(f"folder={folder} resolved to zero rows at {source_glob}")

    logger.info("folder=%s count=%d", folder, row_count)

    _write_json(
        output_path, {"folder": folder, "count": row_count}, use_blob_storage, bucket
    )
