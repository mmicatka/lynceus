# projects/candidates/src/candidates/load_candidates.py

import datetime
import glob
import gzip
import io
import itertools
import time
from collections.abc import Iterator
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.io.staged_io import staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest import Manifest

logger = get_lynceus_logger()

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_BATCH_ROWS = 100_000
DEFAULT_FILES_PER_STAGE = 8
DEFAULT_TRANSFERS = 4

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)


def _parquet_output_path(source_path: Path, output_dir: Path) -> Path:
    name = source_path.name
    stem = name[: -len(".smi.gz")] if name.endswith(".smi.gz") else name
    return output_dir / f"{stem}.parquet"


def _parse_smi_line(line: str) -> tuple[str, str] | None:
    stripped = line.rstrip("\n")
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    smiles = parts[0]
    identifier = parts[1] if len(parts) > 1 else ""
    return smiles, identifier


def _iter_smi_batches(
    path: Path, batch_rows: int, chunk_size: int
) -> Iterator[tuple[list[str], list[str]]]:
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


def _is_converted(source_path: Path, output_path: Path) -> bool:
    return (
        output_path.exists()
        and output_path.stat().st_mtime >= source_path.stat().st_mtime
    )


def _write_parquet(
    source_path: Path,
    output_dir: Path,
    chunk_size: int,
    batch_rows: int,
) -> None:
    output_path = _parquet_output_path(source_path, output_dir)
    with pq.ParquetWriter(output_path, PARQUET_SCHEMA) as writer:
        for smiles_batch, id_batch in _iter_smi_batches(
            source_path, batch_rows, chunk_size
        ):
            table = pa.table(
                {"smiles": smiles_batch, "id": id_batch},
                schema=PARQUET_SCHEMA,
            )
            writer.write_table(table)


def _convert_batch(
    source_files: tuple[Path, ...],
    output_dir: Path,
    chunk_size: int,
    batch_rows: int,
    transfers: int,
    scratch_dir: str | None,
) -> None:
    with staged_io(source_files, output_dir, transfers, scratch_dir) as (
        local_inputs,
        local_output,
    ):
        for local_source in local_inputs:
            _write_parquet(local_source, local_output, chunk_size, batch_rows)


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
    "--files-per-stage",
    type=click.IntRange(min=1),
    default=DEFAULT_FILES_PER_STAGE,
    show_default=True,
    help="Files staged to local scratch, converted, and uploaded per batch.",
)
@click.option(
    "--transfers",
    type=click.IntRange(min=1),
    default=DEFAULT_TRANSFERS,
    show_default=True,
    help="Concurrent file transfers when staging inputs and outputs.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local scratch directory for staging. Defaults to the system temp dir.",
)
@wide_log(logger)
def load_candidates(
    input_path: str,
    output_path: str,
    chunk_size: int,
    batch_rows: int,
    files_per_stage: int,
    transfers: int,
    scratch_dir: str | None,
):
    click.echo(f"Processing {input_path}...")

    input_folder = Path(input_path.rstrip("/")).name
    source_glob = str(Path(input_path) / "*.smi.gz")
    source_paths = sorted(glob.glob(source_glob))

    if not source_paths:
        raise RuntimeError(
            f"folder={input_folder} resolved to zero files at {source_glob}"
        )

    manifest_data = {
        "chunk_size": chunk_size,
        "batch_rows": batch_rows,
    }

    manifest_path = str(Path(output_path).with_suffix(".manifest.json"))

    manifest = Manifest(data=manifest_data, filepath=manifest_path)
    manifest.set_source_files(source_paths, root=input_path)

    try:
        if manifest.exists_superset():
            logger.info("Valid manifest found.")
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_files = [Path(path) for path in source_paths]
    pending = [
        source
        for source in source_files
        if not _is_converted(source, _parquet_output_path(source, output_dir))
    ]
    skipped_count = len(source_files) - len(pending)

    logger.info(
        "Streaming files to parquet",
        folder=input_folder,
        file_count=len(source_files),
        pending=len(pending),
        skipped=skipped_count,
        path=output_path,
    )

    start_time = time.perf_counter()

    for batch in itertools.batched(pending, files_per_stage):
        _convert_batch(
            batch,
            output_dir,
            chunk_size,
            batch_rows,
            transfers,
            scratch_dir,
        )
        logger.info("Processed files", files=[source.name for source in batch])

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished loading candidates",
        folder=input_folder,
        converted=len(pending),
        skipped=skipped_count,
    )
    click.echo("Done!")


if __name__ == "__main__":
    load_candidates()
