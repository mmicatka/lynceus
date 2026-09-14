# modules/local/rebalance_candidates/src/rebalance_candidates/count_candidates.py

import gzip
import json
import logging
from concurrent.futures import ProcessPoolExecutor

import click
from lynceus_utils.cli import NumWorkers
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 256


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


def _resolve_glob_paths(fs, source_glob: str) -> list[str]:
    matches = fs.glob(source_glob)
    if isinstance(matches, dict):
        return list(matches.keys())
    return [str(path) for path in matches]


def _count_lines_in_gzip(fs, path: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> int:
    count = 0
    last_byte = b""
    with fs.open(path, "rb") as raw:
        with gzip.GzipFile(fileobj=raw) as f:
            while chunk := f.read(chunk_size):
                count += chunk.count(b"\n")
                last_byte = chunk[-1:]
    if last_byte and last_byte != b"\n":
        count += 1
    return count


def _count_file_worker(
    path: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
) -> tuple[str, int]:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    return path, _count_lines_in_gzip(fs, path, chunk_size)


def _count_rows_parallel(
    source_paths: list[str],
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    num_workers: int,
) -> int:
    total = 0
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(
                _count_file_worker, path, use_blob_storage, bucket, chunk_size
            )
            for path in source_paths
        ]
        for future in futures:
            path, file_count = future.result()
            total += file_count
            logger.info("counted path=%s rows=%d", path, file_count)
    return total


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
@click.option(
    "--chunk-size",
    type=int,
    default=DEFAULT_CHUNK_SIZE,
    help="Read buffer size in bytes for streaming decompression.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def count_candidates(
    input_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    num_workers: int,
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

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    source_glob = _resolve_source_glob(input_path, use_blob_storage, bucket)
    source_paths = _resolve_glob_paths(fs, source_glob)

    if not source_paths:
        raise RuntimeError(f"folder={folder} resolved to zero files at {source_glob}")

    logger.info(
        "Counting folder=%s across %d files with %d workers",
        folder,
        len(source_paths),
        num_workers,
    )

    row_count = _count_rows_parallel(
        source_paths, use_blob_storage, bucket, chunk_size, num_workers
    )

    if row_count == 0:
        raise RuntimeError(f"folder={folder} resolved to zero rows at {source_glob}")

    logger.info("folder=%s count=%d", folder, row_count)

    _write_json(
        output_path, {"folder": folder, "count": row_count}, use_blob_storage, bucket
    )


if __name__ == "__main__":
    count_candidates()
