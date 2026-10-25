# projects/candidates/src/candidates/load_candidates.py

import datetime
import glob
import gzip
import io
import os
import time
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest import Manifest

logger = get_lynceus_logger()

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_BATCH_ROWS = 100_000

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)


def _parquet_output_path(source_path: str, output_dir: str) -> str:
    filename = os.path.basename(source_path)
    stem = filename[: -len(".smi.gz")] if filename.endswith(".smi.gz") else filename
    return os.path.join(output_dir, f"{stem}.parquet")


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
) -> None:
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
        finally:
            writer.close()


def _write_parquet(
    source_path: str,
    output_dir: str,
    chunk_size: int,
    batch_rows: int,
) -> str:
    resolved_output = _parquet_output_path(source_path, output_dir)
    _write_parquet_from_smi(source_path, resolved_output, chunk_size, batch_rows)
    return source_path


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
@wide_log(logger)
def load_candidates(
    input_path: str,
    output_path: str,
    chunk_size: int,
    batch_rows: int,
):
    click.echo(f"Processing {input_path}...")

    input_folder = os.path.basename(input_path.rstrip("/"))
    source_glob = os.path.join(input_path, "*.smi.gz")
    source_paths = glob.glob(source_glob)

    if not source_paths:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero files at {source_glob}"
        )

    manifest_data = {
        "input_path": input_path,
        "output_path": output_path,
        "source_files": source_paths,
        "chunk_size": chunk_size,
        "batch_rows": batch_rows,
    }

    manifest_path = str(Path(output_path).with_suffix(".manifest.json"))
    manifest = Manifest(data=manifest_data, filepath=manifest_path)

    try:
        if manifest.exists_superset():
            logger.info(
                "Valid manifest found.",
                manifest=manifest.data,
            )
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Streaming files to parquet",
        folder=input_folder,
        file_count=len(source_paths),
        path=output_path,
    )

    start_time = time.perf_counter()

    # Process serially on a single thread
    for path in source_paths:
        processed_path = _write_parquet(
            path,
            output_path,
            chunk_size,
            batch_rows,
        )
        logger.info("Processed file", path=processed_path)

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info("Finished loading candidates", folder=input_folder)
    click.echo("Done!")


if __name__ == "__main__":
    load_candidates()
