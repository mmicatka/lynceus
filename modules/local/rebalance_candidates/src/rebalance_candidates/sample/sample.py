# modules/local/rebalance_candidates/src/rebalance_candidates/sample/sample.py

import json
import logging
import time

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


def _resolve_path(path: str, use_blob_storage: bool, bucket: str) -> str:
    return f"s3://{bucket}/{path.lstrip('/')}" if use_blob_storage else path


def _count_json_path(output_dir: str) -> str:
    return f"{output_dir.rstrip('/')}/count.json"


def _read_json(path: str, fs) -> dict | None:
    if not fs.exists(path):
        return None
    with fs.open(path, "r") as f:
        return json.load(f)


def _write_json(path: str, payload: dict, fs) -> None:
    with fs.open(path, "w") as f:
        f.write(json.dumps(payload))
    logger.info("Wrote sample count to %s", path)


def _folder_row_count(conn, output_dir: str) -> int | None:
    glob = f"{output_dir.rstrip('/')}/*.parquet"
    try:
        res = conn.execute(f"SELECT count(*) FROM read_parquet('{glob}')").fetchone()
    except Exception:
        return None
    return res[0] if res else None


def _validate_source_nonempty(source_row_count: int, folder: str) -> None:
    if source_row_count <= 0:
        raise RuntimeError(
            f"folder={folder} source_row_count must be positive, got {source_row_count}"
        )


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input folder containing Parquet files.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=str,
    help="Output directory for sampled Parquet files.",
)
@click.option(
    "--source-count",
    "source_row_count",
    required=True,
    type=int,
    help="Known row count for the source folder (from merged candidate counts).",
)
@click.option(
    "--target-count",
    "target_count",
    required=True,
    type=int,
    help="Number of rows to sample.",
)
@click.option(
    "--file-size-bytes",
    "file_size_bytes",
    default="512MB",
    show_default=True,
    help="Approximate output Parquet file size before rolling over.",
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
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@click.option(
    "--memory-limit",
    "memory_limit",
    type=str,
    default=None,
    help="Memory limit (e.g. '1500MB')",
)
def sample_candidates(
    input_path: str,
    output_dir: str,
    file_size_bytes: str,
    source_row_count: int,
    target_count: int,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
    memory_limit: str,
) -> None:
    if target_count <= 0:
        raise RuntimeError(f"target_count must be positive, got {target_count}")

    folder = input_path.rstrip("/").split("/")[-1]

    _validate_source_nonempty(source_row_count, folder)

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    conn = get_connection(
        blob_storage_settings, threads=num_workers, memory_limit=memory_limit
    )

    source_glob = _resolve_path(
        f"{input_path.rstrip('/')}/*.parquet", use_blob_storage, bucket
    )
    resolved_output_dir = _resolve_path(output_dir, use_blob_storage, bucket)
    count_json_path = _count_json_path(resolved_output_dir)

    existing = _read_json(count_json_path, fs)
    if existing is not None:
        existing_row_count = _folder_row_count(conn, resolved_output_dir)
        if existing_row_count is not None and existing_row_count == existing.get(
            "count"
        ):
            logger.info(
                "folder=%s already has %d rows at %s, skipping",
                folder,
                existing_row_count,
                resolved_output_dir,
            )
            return

    logger.info(
        "folder=%s sampling %d rows from %d (source=%s)",
        folder,
        target_count,
        source_row_count,
        source_glob,
    )

    sample_start = time.monotonic()

    if source_row_count <= target_count:
        logger.info(
            "folder=%s source_row_count <= target_count, taking full source",
            folder,
        )
        select_query = f"""
            SELECT smiles, id, '{folder}' AS folder
            FROM read_parquet('{source_glob}')
        """
    else:
        sample_fraction = min(1.0, (target_count / source_row_count) * 1.05)
        logger.info(
            "folder=%s sample_fraction=%.4f%% (system sampling, row-group granularity)",
            folder,
            sample_fraction * 100,
        )
        select_query = f"""
            SELECT smiles, id, '{folder}' AS folder
            FROM read_parquet('{source_glob}')
            USING SAMPLE {sample_fraction * 100} PERCENT (system)
            LIMIT {target_count}
        """

    logger.info(
        "folder=%s streaming sampled output to %s (file_size_bytes=%s)",
        folder,
        resolved_output_dir,
        file_size_bytes,
    )

    copy_query = f"""
        COPY (
            {select_query}
        ) TO '{resolved_output_dir}'
        (FORMAT PARQUET, COMPRESSION 'zstd', FILE_SIZE_BYTES '{file_size_bytes}')
    """

    conn.execute(copy_query)

    elapsed = time.monotonic() - sample_start
    logger.info("folder=%s sample+export took %.1fs", folder, elapsed)

    row_count = _folder_row_count(conn, resolved_output_dir)
    if row_count is None or row_count == 0:
        raise RuntimeError(
            f"Sampled output for folder={folder} is empty: {resolved_output_dir}"
        )

    if row_count < target_count:
        logger.warning(
            "folder=%s produced %d rows, less than requested target_count=%d "
            "(source folder smaller than allocation)",
            folder,
            row_count,
            target_count,
        )

    logger.info("folder=%s wrote %d rows to %s", folder, row_count, resolved_output_dir)

    _write_json(
        count_json_path,
        {"folder": folder, "count": row_count},
        fs,
    )
