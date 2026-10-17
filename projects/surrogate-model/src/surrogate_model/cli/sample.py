# projects/surrogate-model/src/surrogate_model/cli/sample.py

import contextlib
import glob
import json
import os
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

import click
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from lynceus_core.logging import wide_log

PARQUET_PATTERN = "*.parquet"
MARKER_SUFFIX = ".success"
TEMP_SUFFIX = ".tmp"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000
PROGRESS_INTERVAL_SECONDS = 15.0


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


class ProgressReporter:
    def __init__(
        self,
        total_rows: int,
        identifier: str,
        interval: float = PROGRESS_INTERVAL_SECONDS,
    ) -> None:
        self._total_rows = total_rows
        self._identifier = identifier
        self._interval = interval
        self._started = time.monotonic()
        self._last_report = self._started

    def update(self, scanned_rows: int) -> None:
        now = time.monotonic()
        finished = scanned_rows >= self._total_rows
        if not finished and now - self._last_report < self._interval:
            return
        self._last_report = now
        logger.info(
            "Sampling in progress",
            identifier=self._identifier,
            scanned_rows=scanned_rows,
            total_rows=self._total_rows,
            percent=round(100 * scanned_rows / max(self._total_rows, 1), 1),
            elapsed_seconds=round(now - self._started, 1),
        )


def _marker_path(output_path: str) -> str:
    return f"{output_path}{MARKER_SUFFIX}"


def _output_is_valid(output_path: str, num_samples: int) -> bool:
    marker_path = _marker_path(output_path)
    if not (os.path.isfile(output_path) and os.path.isfile(marker_path)):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_samples") == num_samples


def _write_success_marker(output_path: str, num_samples: int) -> None:
    with open(_marker_path(output_path), "w") as f:
        json.dump({"num_samples": num_samples}, f)


def _resolve_parquet_files(pattern: str) -> list[str]:
    files: list[str] = []
    for match in sorted(glob.glob(pattern, recursive=True)):
        if os.path.isdir(match):
            files.extend(sorted(glob.glob(os.path.join(match, PARQUET_PATTERN))))
        else:
            files.append(match)

    unique_files = list(dict.fromkeys(files))
    if not unique_files:
        raise RuntimeError(f"Resolved zero parquet files at {pattern}")
    return unique_files


def _count_rows(files: list[str]) -> int:
    return sum(pq.ParquetFile(path).metadata.num_rows for path in files)


def _select_positions(
    total_rows: int, num_samples: int, seed: int | None
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(total_rows, size=num_samples, replace=False))


def _stream_batches(
    files: list[str],
    columns: list[str] | None,
    batch_size: int,
) -> Iterator[pa.RecordBatch]:
    for path in files:
        yield from pq.ParquetFile(path).iter_batches(
            batch_size=batch_size, columns=columns
        )


def _rechunk(batches: Iterable[pa.RecordBatch], size: int) -> Iterator[pa.Table]:
    pending: list[pa.RecordBatch] = []
    pending_rows = 0
    for batch in batches:
        pending.append(batch)
        pending_rows += batch.num_rows
        while pending_rows >= size:
            table = pa.Table.from_batches(pending)
            yield table.slice(0, size)
            remainder = table.slice(size)
            pending = remainder.to_batches()
            pending_rows = remainder.num_rows
    if pending_rows:
        yield pa.Table.from_batches(pending)


def _aligned_chunks(
    features_files: list[str],
    conformers_files: list[str],
    id_column: str,
    batch_size: int,
) -> Iterator[tuple[pa.Table, pa.Table]]:
    features = _rechunk(_stream_batches(features_files, None, batch_size), batch_size)
    conformers = _rechunk(
        _stream_batches(conformers_files, [id_column, CONFORMER_COLUMN], batch_size),
        batch_size,
    )
    for features_chunk, conformers_chunk in zip(features, conformers, strict=True):
        if features_chunk.num_rows != conformers_chunk.num_rows:
            raise ValueError("Features and conformers chunks differ in row count")
        yield features_chunk, conformers_chunk


def _select_aligned(
    features: pa.Table,
    conformers: pa.Table,
    local_positions: np.ndarray,
    id_column: str,
) -> pa.Table:
    indices = pa.array(local_positions, type=pa.int64())
    selected_features = features.take(indices)
    selected_conformers = conformers.take(indices)
    if not selected_features[id_column].equals(selected_conformers[id_column]):
        raise ValueError(f"Misaligned inputs: '{id_column}' differs between sides")
    return selected_features.append_column(
        CONFORMER_COLUMN, selected_conformers[CONFORMER_COLUMN]
    )


def _write_sample(
    features_files: list[str],
    conformers_files: list[str],
    positions: np.ndarray,
    output_file: str,
    id_column: str,
    batch_size: int,
    reporter: ProgressReporter,
) -> None:
    writer: pq.ParquetWriter | None = None
    offset = 0
    try:
        for features, conformers in _aligned_chunks(
            features_files, conformers_files, id_column, batch_size
        ):
            end = offset + features.num_rows
            lo, hi = np.searchsorted(positions, [offset, end])
            selected = _select_aligned(
                features, conformers, positions[lo:hi] - offset, id_column
            )
            if writer is None:
                writer = pq.ParquetWriter(
                    output_file, selected.schema, compression=COMPRESSION
                )
            writer.write_table(selected)
            offset = end
            reporter.update(offset)
    finally:
        if writer is not None:
            writer.close()


def _write_sample_atomically(
    features_files: list[str],
    conformers_files: list[str],
    positions: np.ndarray,
    output_path: str,
    id_column: str,
    batch_size: int,
    reporter: ProgressReporter,
) -> None:
    temp_path = f"{output_path}{TEMP_SUFFIX}"
    try:
        _write_sample(
            features_files=features_files,
            conformers_files=conformers_files,
            positions=positions,
            output_file=temp_path,
            id_column=id_column,
            batch_size=batch_size,
            reporter=reporter,
        )
        written = pq.ParquetFile(temp_path).metadata.num_rows
        if written != len(positions):
            raise RuntimeError(f"Wrote {written} rows, expected {len(positions)}")
        os.replace(temp_path, output_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(temp_path)
        raise


@click.command("sample_aligned")
@click.option(
    "--features-input",
    "features_input",
    required=True,
    type=str,
    help="Features parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--conformers-input",
    "conformers_input",
    required=True,
    type=str,
    help="Conformer parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output parquet file path.",
)
@click.option(
    "--num-samples",
    "num_samples",
    required=True,
    type=click.IntRange(min=1),
    help="Total number of samples to pull.",
)
@click.option(
    "--id-column",
    "id_column",
    default="id",
    show_default=True,
    type=str,
    help="ID column used to verify row alignment.",
)
@click.option(
    "--batch-size",
    "batch_size",
    default=DEFAULT_BATCH_SIZE,
    show_default=True,
    type=click.IntRange(min=1),
    help="Rows read per chunk from each input.",
)
@click.option(
    "--seed",
    "seed",
    default=None,
    type=int,
    help="Seed for reproducible sampling.",
)
@wide_log(logger)
def sample_candidates(
    features_input: str,
    conformers_input: str,
    output_path: str,
    num_samples: int,
    id_column: str,
    batch_size: int,
    seed: int | None,
) -> None:
    click.echo(
        f"Processing aligned samples from {features_input} and {conformers_input}..."
    )

    identifier = Path(output_path).stem

    if _output_is_valid(output_path, num_samples):
        logger.info(
            "Sample already valid, skipping generation",
            identifier=identifier,
            num_samples=num_samples,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    features_files = _resolve_parquet_files(features_input)
    conformers_files = _resolve_parquet_files(conformers_input)

    total_rows = _count_rows(features_files)
    conformer_rows = _count_rows(conformers_files)
    if total_rows != conformer_rows:
        raise RuntimeError(
            f"Row count mismatch: {total_rows} features vs {conformer_rows} conformers"
        )

    effective_samples = min(num_samples, total_rows)
    if effective_samples < num_samples:
        logger.warning(
            "Requested more samples than available rows, returning all rows",
            identifier=identifier,
            requested=num_samples,
            available=total_rows,
        )

    logger.info(
        "Executing aligned position sampling",
        features_source=features_input,
        conformers_source=conformers_input,
        num_features_files=len(features_files),
        num_conformers_files=len(conformers_files),
        identifier=identifier,
        total_rows=total_rows,
        num_samples=effective_samples,
        output_path=output_path,
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    positions = _select_positions(total_rows, effective_samples, seed)

    _write_sample_atomically(
        features_files=features_files,
        conformers_files=conformers_files,
        positions=positions,
        output_path=output_path,
        id_column=id_column,
        batch_size=batch_size,
        reporter=ProgressReporter(total_rows, identifier),
    )

    _write_success_marker(output_path, num_samples)

    logger.info(
        "Finished aligned position sampling",
        identifier=identifier,
        num_samples=effective_samples,
        output_path=output_path,
    )
    click.echo("Done!")
