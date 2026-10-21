# projects/surrogate-model/src/surrogate_model/cli/sample.py

import glob
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

import click
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger, wide_log

PARQUET_PATTERN = "*.parquet"
MARKER_SUFFIX = ".success"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000


logger = get_lynceus_logger()


def _marker_path(output_path: str) -> str:
    return f"{output_path}{MARKER_SUFFIX}"


def _output_is_valid(output_path: str, num_samples: int) -> bool:
    marker_path = _marker_path(output_path)
    if not (os.path.isfile(output_path) and os.path.isfile(marker_path)):
        return False
    with open(marker_path, "r") as f:
        if json.load(f).get("num_samples") != num_samples:
            return False
    return os.path.getsize(output_path) > 0


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
    finally:
        if writer is not None:
            writer.close()


def _verify_written(output_path: str, expected_rows: int) -> None:
    written = pq.ParquetFile(output_path).metadata.num_rows
    if written != expected_rows:
        raise RuntimeError(f"Wrote {written} rows, expected {expected_rows}")


def _write_sample_with_marker(
    features_files: list[str],
    conformers_files: list[str],
    positions: np.ndarray,
    output_path: str,
    num_samples: int,
    id_column: str,
    batch_size: int,
) -> None:
    _write_sample(
        features_files=features_files,
        conformers_files=conformers_files,
        positions=positions,
        output_file=output_path,
        id_column=id_column,
        batch_size=batch_size,
    )
    _verify_written(output_path, len(positions))
    _write_success_marker(output_path, num_samples)


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

    _write_sample_with_marker(
        features_files=features_files,
        conformers_files=conformers_files,
        positions=positions,
        output_path=output_path,
        num_samples=num_samples,
        id_column=id_column,
        batch_size=batch_size,
    )

    logger.info(
        "Finished aligned position sampling",
        identifier=identifier,
        num_samples=effective_samples,
        output_path=output_path,
    )
    click.echo("Done!")
