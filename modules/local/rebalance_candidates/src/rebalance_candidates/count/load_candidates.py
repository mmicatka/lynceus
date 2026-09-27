# modules/local/rebalance_candidates/src/rebalance_candidates/count_candidates.py

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


def _resolve_source_glob(input_path: str, use_blob_storage: bool, bucket: str) -> str:
    pattern = f"{input_path.rstrip('/')}/*.smi.gz"
    return _resolve_path(pattern, use_blob_storage, bucket)


def _folder_output_dir(output_dir: str, folder: str) -> str:
    return f"{output_dir.rstrip('/')}/{folder}"


def _json_output_path(output_dir: str, folder: str) -> str:
    return f"{output_dir.rstrip('/')}/{folder}/count.json"


def _folder_row_count(conn, output_dir: str) -> int | None:
    glob = f"{output_dir.rstrip('/')}/*.parquet"
    try:
        res = conn.execute(f"SELECT count(*) FROM read_parquet('{glob}')").fetchone()
    except Exception:
        return None
    return res[0] if res else None


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
@click.option("--bucket", type=str, help="S3-compatible bucket name.")
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
def load_candidates(
    input_path: str,
    output_path: str,
    file_size_bytes: str,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
    memory_limit: str,
) -> None:
    input_folder = input_path.rstrip("/").split("/")[-1]

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    conn = get_connection(
        blob_storage_settings, threads=num_workers, memory_limit=memory_limit
    )

    source_glob = _resolve_source_glob(input_path, use_blob_storage, bucket)
    folder_output_dir = _resolve_path(
        _folder_output_dir(output_path, input_folder), use_blob_storage, bucket
    )
    final_output_path = _json_output_path(output_path, input_folder)

    existing = _read_json(final_output_path, use_blob_storage, bucket)
    if existing is not None:
        existing_row_count = _folder_row_count(conn, folder_output_dir)
        if existing_row_count is not None and existing_row_count == existing.get(
            "count"
        ):
            logger.info(
                "folder=%s already has %d rows at %s, skipping",
                input_folder,
                existing_row_count,
                folder_output_dir,
            )
            return

    logger.info(
        "folder=%s streaming %s to parquet at %s (file_size_bytes=%s)",
        input_folder,
        source_glob,
        folder_output_dir,
        file_size_bytes,
    )

    copy_query = f"""
        COPY (
            SELECT smiles, id
            FROM read_csv(
                '{source_glob}',
                delim = '\\t',
                header = false,
                columns = {{'smiles': 'VARCHAR', 'id': 'VARCHAR'}}
            )
            WHERE trim(smiles) != ''
        ) TO '{folder_output_dir}'
        (FORMAT PARQUET, COMPRESSION 'zstd', FILE_SIZE_BYTES '{file_size_bytes}')
    """

    conn.execute(copy_query)

    row_count = _folder_row_count(conn, folder_output_dir)
    if row_count is None or row_count == 0:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero rows at {source_glob}"
        )

    logger.info("folder=%s count=%d", input_folder, row_count)

    _write_json(
        final_output_path,
        {"folder": input_folder, "count": row_count},
        use_blob_storage,
        bucket,
    )
