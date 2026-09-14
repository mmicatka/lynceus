# modules/local/rebalance_candidates/src/rebalance_candidates/sample/sample.py

import logging

import click
from duckdb import IOException
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _existing_output_row_count(conn, output_path: str) -> int | None:
    try:
        result = conn.read_parquet(output_path).count("*").fetchone()
    except IOException:
        return None

    if result is None:
        return None

    return result[0]


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input folder",
)
@click.option(
    "--target-count",
    "target_count",
    required=True,
    type=int,
    help="Number of rows to sample.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output Parquet file path.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read source and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def sample_candidates(
    input_path: str,
    target_count: int,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    if target_count <= 0:
        raise RuntimeError(f"target_count must be positive, got {target_count}")

    folder = input_path.rstrip("/").split("/")[-1]
    source_glob = f"{input_path.rstrip('/')}/*.smi.gz"

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        source_glob = f"s3://{bucket}/{source_glob.lstrip('/')}"
        output_path = f"s3://{bucket}/{output_path.lstrip('/')}"
    else:
        conn = get_connection()

    existing_row_count = _existing_output_row_count(conn, output_path)
    if existing_row_count == target_count:
        logger.info(
            "folder=%s already has %d rows at %s, skipping",
            folder,
            existing_row_count,
            output_path,
        )
        return

    logger.info(
        "Sampling folder=%s target_count=%d from %s", folder, target_count, source_glob
    )

    sampled_rel = conn.sql(
        f"""
        SELECT smiles, id, '{folder}' AS folder
        FROM read_csv(
            '{source_glob}',
            delim='\t',
            header=False,
            columns={{'smiles': 'VARCHAR', 'id': 'VARCHAR'}}
        )
        USING SAMPLE {target_count} ROWS
        """
    )

    export_parquet(conn, sampled_rel, output_path)

    row_count = conn.read_parquet(output_path).count("*").fetchone()
    if row_count is None or row_count[0] == 0:
        raise RuntimeError(
            f"Sampled output for folder={folder} is empty: {output_path}"
        )

    actual_rows = row_count[0]
    if actual_rows < target_count:
        logger.warning(
            "folder=%s produced %d rows, less than requested target_count=%d "
            "(source folder smaller than allocation)",
            folder,
            actual_rows,
            target_count,
        )

    logger.info("folder=%s wrote %d rows to %s", folder, actual_rows, output_path)
