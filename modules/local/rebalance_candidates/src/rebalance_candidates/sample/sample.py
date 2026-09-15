# modules/local/rebalance_candidates/src/rebalance_candidates/sample/sample.py

import logging

import click
from duckdb import IOException
from lynceus_utils.duckdb import export_parquet, file_exists, get_connection
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


def _ensure_converted_parquet(
    conn, source_glob: str, converted_path: str, folder: str
) -> None:
    if file_exists(conn, converted_path):
        existing_count = _existing_output_row_count(conn, converted_path)
        if existing_count is not None and existing_count > 0:
            logger.info(
                "folder=%s converted parquet already exists at %s with %d rows,"
                " skipping conversion",
                folder,
                converted_path,
                existing_count,
            )
            return
        raise RuntimeError(
            f"folder={folder} converted_path={converted_path} exists but is"
            " empty or unreadable, refusing to proceed"
        )

    logger.info(
        "folder=%s converting gzip CSV at %s to parquet at %s",
        folder,
        source_glob,
        converted_path,
    )

    conn.execute(
        f"""
        COPY (
            SELECT smiles, id, '{folder}' AS folder
            FROM read_csv(
                '{source_glob}',
                delim='\t',
                header=False,
                columns={{'smiles': 'VARCHAR', 'id': 'VARCHAR'}}
            )
        ) TO '{converted_path}' (FORMAT PARQUET, COMPRESSION 'zstd')
        """
    )

    if not file_exists(conn, converted_path):
        raise RuntimeError(
            f"folder={folder} conversion reported success but {converted_path}"
            " is not readable back"
        )

    converted_count = _existing_output_row_count(conn, converted_path)
    if converted_count is None or converted_count == 0:
        raise RuntimeError(
            f"folder={folder} converted parquet at {converted_path} is empty"
        )

    logger.info(
        "folder=%s wrote %d rows to converted parquet at %s",
        folder,
        converted_count,
        converted_path,
    )


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
    "--parquet-prefix",
    "parquet_prefix",
    required=True,
    type=str,
    help="Folder to store converted gzip-CSV-to-Parquet intermediates.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read source and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option(
    "--source-count",
    "source_row_count",
    required=True,
    type=int,
    help="Known row count for the source folder (from merged candidate counts).",
)
def sample_candidates(
    input_path: str,
    target_count: int,
    source_row_count: int,
    output_path: str,
    parquet_prefix: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    if target_count <= 0:
        raise RuntimeError(f"target_count must be positive, got {target_count}")
    if source_row_count <= 0:
        raise RuntimeError(f"source_row_count must be positive, got {source_row_count}")

    folder = input_path.rstrip("/").split("/")[-1]
    source_glob = f"{input_path.rstrip('/')}/*.smi.gz"
    converted_path = f"{parquet_prefix.rstrip('/')}/{folder}_converted.parquet"

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        source_glob = f"s3://{bucket}/{source_glob.lstrip('/')}"
        output_path = f"s3://{bucket}/{output_path.lstrip('/')}"
        converted_path = f"s3://{bucket}/{converted_path.lstrip('/')}"
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

    _ensure_converted_parquet(conn, source_glob, converted_path, folder)

    logger.info(
        "sampling %d rows from %d for %s", target_count, source_row_count, folder
    )

    if source_row_count <= target_count:
        sampled_rel = conn.sql(
            f"SELECT smiles, id, folder FROM read_parquet('{converted_path}')"
        )
    else:
        sample_fraction = min(1.0, (target_count / source_row_count) * 1.05)
        sampled_rel = conn.sql(
            f"""
            SELECT smiles, id, folder
            FROM read_parquet('{converted_path}')
            USING SAMPLE {sample_fraction * 100} PERCENT (bernoulli)
            LIMIT {target_count}
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
