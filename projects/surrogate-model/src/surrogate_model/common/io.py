# projects/surrogate-model/src/surrogate_model/common/io.py


import glob
import os
from collections.abc import Iterable, Iterator

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

PARQUET_PATTERN = "*.parquet"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000


def resolve_parquet_files(pattern: str) -> list[str]:
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


def count_rows(files: list[str]) -> int:
    return sum(pq.ParquetFile(path).metadata.num_rows for path in files)


def stream_batches(
    files: list[str], columns: list[str] | None, batch_size: int
) -> Iterator[pa.RecordBatch]:
    for path in files:
        yield from pq.ParquetFile(path).iter_batches(
            batch_size=batch_size, columns=columns
        )


def rechunk(batches: Iterable[pa.RecordBatch], size: int) -> Iterator[pa.Table]:
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


def stream_tables(
    files: list[str], columns: list[str] | None, batch_size: int
) -> Iterator[pa.Table]:
    return rechunk(stream_batches(files, columns, batch_size), batch_size)


def aligned_chunks(
    features_files: list[str],
    conformers_files: list[str],
    id_column: str,
    batch_size: int,
) -> Iterator[tuple[pa.Table, pa.Table]]:
    features = stream_tables(features_files, None, batch_size)
    conformers = stream_tables(
        conformers_files, [id_column, CONFORMER_COLUMN], batch_size
    )
    for features_chunk, conformers_chunk in zip(features, conformers, strict=True):
        if features_chunk.num_rows != conformers_chunk.num_rows:
            raise ValueError("Features and conformers chunks differ in row count")
        yield features_chunk, conformers_chunk


def select_aligned(
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


def write_aligned_selection(
    features_files: list[str],
    conformers_files: list[str],
    positions: np.ndarray,
    output_file: str,
    id_column: str,
    batch_size: int,
    extra_columns: dict[str, np.ndarray] | None = None,
) -> None:
    positions = np.sort(positions)
    extra = extra_columns or {}
    writer: pq.ParquetWriter | None = None
    offset = 0
    try:
        for features, conformers in aligned_chunks(
            features_files, conformers_files, id_column, batch_size
        ):
            end = offset + features.num_rows
            lo, hi = np.searchsorted(positions, [offset, end])
            selected = select_aligned(
                features, conformers, positions[lo:hi] - offset, id_column
            )
            for name, values in extra.items():
                selected = selected.append_column(name, pa.array(values[lo:hi]))
            if writer is None:
                writer = pq.ParquetWriter(
                    output_file, selected.schema, compression=COMPRESSION
                )
            writer.write_table(selected)
            offset = end
    finally:
        if writer is not None:
            writer.close()


def verify_written(output_path: str, expected_rows: int) -> None:
    written = pq.ParquetFile(output_path).metadata.num_rows
    if written != expected_rows:
        raise RuntimeError(f"Wrote {written} rows, expected {expected_rows}")
