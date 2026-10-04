# projects/candidates/src/candidates/load_candidates.py

import glob
import gzip
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import click
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_BATCH_ROWS = 100_000

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)


def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None

    with open(path, "r") as f:
        return json.load(f)


def _write_json(output_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f)

    logger.info("Wrote candidate count", path=output_path)


def _folder_output_dir(output_dir: str, folder: str) -> str:
    return os.path.join(output_dir, folder)


def _json_output_path(output_dir: str, folder: str) -> str:
    return os.path.join(output_dir, folder, "count.json")


def _parquet_output_path(source_path: str, output_dir: str) -> str:
    filename = os.path.basename(source_path)
    stem = filename[: -len(".smi.gz")] if filename.endswith(".smi.gz") else filename
    return os.path.join(output_dir, f"{stem}.parquet")


def _clear_stale_parquet(output_dir: str) -> None:
    pattern = os.path.join(output_dir, "*.parquet")
    for path in glob.glob(pattern):
        os.remove(path)


def _folder_row_count(output_dir: str) -> int | None:
    pattern = os.path.join(output_dir, "*.parquet")
    paths = glob.glob(pattern)
    if not paths:
        return None

    total = 0
    for path in paths:
        with open(path, "rb") as f:
            total += pq.ParquetFile(f).metadata.num_rows
    return total


def _parse_smi_line(line: str) -> tuple[str, str] | None:
    stripped = line.rstrip("\n")
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    smiles = parts[0]
    identifier = parts[1] if len(parts) > 1 else ""
    return smiles, identifier


def _iter_smi_batches(path: str, batch_rows: int, chunk_size: int):
    smiles_batch: list[str] = []
    id_batch: list[str] = []

    with open(path, "rb", buffering=chunk_size) as raw:
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


def _write_parquet_from_smi(
    source_path: str,
    resolved_output: str,
    chunk_size: int,
    batch_rows: int,
) -> tuple[str, int]:
    row_count = 0
    os.makedirs(os.path.dirname(resolved_output), exist_ok=True)

    with open(resolved_output, "wb") as out_f:
        writer = pq.ParquetWriter(out_f, PARQUET_SCHEMA)
        try:
            for smiles_batch, id_batch in _iter_smi_batches(
                source_path, batch_rows, chunk_size
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
    chunk_size: int,
    batch_rows: int,
) -> tuple[str, int]:
    resolved_output = _parquet_output_path(source_path, output_dir)

    if os.path.exists(resolved_output):
        row_count = _parquet_row_count(resolved_output)
        logger.info(
            "Parquet already exists, skipping write",
            path=resolved_output,
            rows=row_count,
        )
        return source_path, row_count

    return _write_parquet_from_smi(source_path, resolved_output, chunk_size, batch_rows)


def _parquet_row_count(resolved_path: str) -> int:
    with open(resolved_path, "rb") as f:
        return pq.ParquetFile(f).metadata.num_rows


def _write_parquet_parallel(
    source_paths: list[str],
    output_dir: str,
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
                chunk_size,
                batch_rows,
            )
            for path in source_paths
        ]
        for future in futures:
            path, file_count = future.result()
            total += file_count
            logger.info("Wrote parquet", path=path, rows=file_count)
    return total


@click.command("load_candidates")
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
    "--chunk-size",
    type=int,
    default=DEFAULT_CHUNK_SIZE,
    show_default=True,
    help="Read buffer size in bytes for streaming decompression.",
)
@click.option(
    "--batch-rows",
    type=int,
    default=DEFAULT_BATCH_ROWS,
    show_default=True,
    help="Number of rows to buffer before flushing a Parquet row group.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def load_candidates(
    input_path: str,
    output_path: str,
    chunk_size: int,
    batch_rows: int,
    num_workers: int,
):
    click.echo(f"Processing {input_path}...")

    input_folder = os.path.basename(input_path.rstrip("/"))
    source_glob = os.path.join(input_path, "*.smi.gz")
    source_paths = glob.glob(source_glob)

    if not source_paths:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero files at {source_glob}"
        )

    folder_output_dir = _folder_output_dir(output_path, input_folder)
    final_output_path = _json_output_path(output_path, input_folder)

    existing = _read_json(final_output_path)
    existing_row_count = (
        _folder_row_count(folder_output_dir) if existing is not None else None
    )

    if existing is not None and existing_row_count == existing.get("count"):
        logger.info(
            "Folder already processed, skipping",
            folder=input_folder,
            rows=existing_row_count,
            path=folder_output_dir,
        )
        click.echo("Done!")
        return

    if existing is None:
        logger.warning(
            "Manifest missing, clearing stale parquet",
            folder=input_folder,
            manifest_path=final_output_path,
            parquet_dir=folder_output_dir,
        )
    else:
        logger.warning(
            "Count mismatch, clearing stale parquet",
            folder=input_folder,
            manifest_count=existing.get("count"),
            actual_count=existing_row_count,
            parquet_dir=folder_output_dir,
        )

    _clear_stale_parquet(folder_output_dir)

    logger.info(
        "Streaming files to parquet",
        folder=input_folder,
        file_count=len(source_paths),
        path=folder_output_dir,
        workers=num_workers,
    )

    row_count = _write_parquet_parallel(
        source_paths,
        folder_output_dir,
        chunk_size,
        batch_rows,
        num_workers,
    )

    if row_count == 0:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero rows at {source_glob}"
        )

    logger.info(
        "Finished loading candidates", folder=input_folder, total_rows=row_count
    )

    _write_json(
        final_output_path,
        {"folder": input_folder, "count": row_count},
    )

    click.echo("Done!")
