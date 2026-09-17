# modules/local/rebalance_candidates/src/rebalance_candidates/count_candidates.py

import gzip
import io
import json
import logging
from concurrent.futures import ProcessPoolExecutor

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.cli import NumWorkers
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_BATCH_ROWS = 100_000

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)


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


def _source_filename(path: str) -> str:
    return path.rstrip("/").split("/")[-1]


def _parquet_output_path(source_path: str, output_dir: str) -> str:
    filename = _source_filename(source_path)
    stem = filename[: -len(".smi.gz")] if filename.endswith(".smi.gz") else filename
    return f"{output_dir.rstrip('/')}/{stem}.parquet"


def _parse_smi_line(line: str) -> tuple[str, str] | None:
    stripped = line.rstrip("\n")
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    smiles = parts[0]
    identifier = parts[1] if len(parts) > 1 else ""
    return smiles, identifier


def _iter_smi_batches(fs, path: str, batch_rows: int, chunk_size: int):
    smiles_batch: list[str] = []
    id_batch: list[str] = []

    with fs.open(path, "rb", block_size=chunk_size) as raw:
        with gzip.GzipFile(fileobj=raw) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
                for line in text_stream:
                    parsed = _parse_smi_line(line)
                    if parsed is None:
                        continue
                    smiles, identifier = parsed
                    smiles_batch.append(smiles)
                    id_batch.append(identifier)

                    if len(smiles_batch) >= batch_rows:
                        yield smiles_batch, id_batch
                        smiles_batch = []
                        id_batch = []

    if smiles_batch:
        yield smiles_batch, id_batch


def _parquet_row_count(fs, resolved_path: str) -> int:
    """Row count of an existing Parquet file via its metadata (no full read)."""
    with fs.open(resolved_path, "rb") as f:
        return pq.ParquetFile(f).metadata.num_rows


def _write_parquet_from_smi(
    source_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    batch_rows: int,
) -> tuple[str, int]:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_output = _resolve_path(output_path, use_blob_storage, bucket)

    row_count = 0

    with fs.open(resolved_output, "wb") as out_f:
        writer = pq.ParquetWriter(out_f, PARQUET_SCHEMA)
        try:
            for smiles_batch, id_batch in _iter_smi_batches(
                fs, source_path, batch_rows, chunk_size
            ):
                table = pa.table(
                    {"smiles": smiles_batch, "id": id_batch}, schema=PARQUET_SCHEMA
                )
                writer.write_table(table)
                row_count += len(smiles_batch)
        finally:
            writer.close()

    return source_path, row_count


def _write_parquet_worker(
    source_path: str,
    output_dir: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    batch_rows: int,
) -> tuple[str, int]:
    output_path = _parquet_output_path(source_path, output_dir)
    resolved_output = _resolve_path(output_path, use_blob_storage, bucket)

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    if fs.exists(resolved_output):
        row_count = _parquet_row_count(fs, resolved_output)
        logger.info(
            "parquet already exists path=%s rows=%d, skipping write",
            resolved_output,
            row_count,
        )
        return source_path, row_count

    return _write_parquet_from_smi(
        source_path, output_path, use_blob_storage, bucket, chunk_size, batch_rows
    )


def _write_parquet_parallel(
    source_paths: list[str],
    output_dir: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    batch_rows: int,
    num_workers: int,
) -> int:
    total = 0
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(
                _write_parquet_worker,
                path,
                output_dir,
                use_blob_storage,
                bucket,
                chunk_size,
                batch_rows,
            )
            for path in source_paths
        ]
        for future in futures:
            path, file_count = future.result()
            total += file_count
            logger.info("wrote parquet path=%s rows=%d", path, file_count)
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
    "--parquet-output",
    "parquet_output_dir",
    required=True,
    type=str,
    help="Output folder for the per-file Parquet files.",
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
    "--batch-rows",
    type=int,
    default=DEFAULT_BATCH_ROWS,
    help="Number of rows to buffer before flushing a Parquet row group.",
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
    parquet_output_dir: str,
    use_blob_storage: bool,
    bucket: str,
    chunk_size: int,
    batch_rows: int,
    num_workers: int,
) -> None:
    folder = input_path.rstrip("/").split("/")[-1]

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    source_glob = _resolve_source_glob(input_path, use_blob_storage, bucket)
    source_paths = _resolve_glob_paths(fs, source_glob)

    if not source_paths:
        raise RuntimeError(f"folder={folder} resolved to zero files at {source_glob}")

    logger.info(
        "Streaming folder=%s across %d files to parquet at %s with %d workers",
        folder,
        len(source_paths),
        parquet_output_dir,
        num_workers,
    )

    row_count = _write_parquet_parallel(
        source_paths,
        parquet_output_dir,
        use_blob_storage,
        bucket,
        chunk_size,
        batch_rows,
        num_workers,
    )

    if row_count == 0:
        raise RuntimeError(f"folder={folder} resolved to zero rows at {source_glob}")

    logger.info("folder=%s count=%d", folder, row_count)

    existing = _read_json(output_path, use_blob_storage, bucket)
    if existing is not None and existing.get("count") == row_count:
        logger.info(
            "folder=%s count unchanged (count=%d), leaving %s as-is",
            folder,
            row_count,
            output_path,
        )
        return

    _write_json(
        output_path, {"folder": folder, "count": row_count}, use_blob_storage, bucket
    )
