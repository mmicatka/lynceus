# modules/local/rebalance_candidates/src/rebalance_candidates/count_candidates.py

import json
import logging

import click
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--input",
    required=True,
    type=str,
    help="Input folder",
)
@click.option(
    "--output",
    required=True,
    type=str,
    help="Output path for the candidate count JSON.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read source via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def count_candidates(
    input: str,
    output: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    folder = input.rstrip("/").split("/")[-1]
    source_glob = f"{input.rstrip('/')}/*.smi.gz"

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

    with open(output, "w") as f:
        json.dump({"tranche": folder, "count": row_count}, f)
