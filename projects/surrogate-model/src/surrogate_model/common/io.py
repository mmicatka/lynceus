# projects/surrogate-model/src/surrogate_model/common/io.py


import glob
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger

from surrogate_model.common.model import ProbabilisticClassifier

PARQUET_PATTERN = "*.parquet"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000

STAGED_MODEL_TRANSFERS = 1
logger = get_lynceus_logger()


def save_model(model: ProbabilisticClassifier[Any], path: Path) -> None:
    logger.info("Saving model", path=str(path))
    with open(path, "wb") as f:
        joblib.dump(model, f)
    logger.info("Model saved successfully", path=str(path))


def save_model_staged(
    model: ProbabilisticClassifier[Any],
    model_path: str | Path,
    scratch_dir: str | None,
) -> None:
    target = Path(model_path)
    with staged_output(
        target.parent,
        transfers=STAGED_MODEL_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        save_model(model, local_output / target.name)


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
    featurized_files: list[str],
    preprocessed_files: list[str],
    id_column: str,
    batch_size: int,
) -> Iterator[tuple[pa.Table, pa.Table]]:
    featurized = stream_tables(featurized_files, None, batch_size)
    preprocessed = stream_tables(
        preprocessed_files, [id_column, CONFORMER_COLUMN], batch_size
    )
    for featurized_chunk, preprocessed_chunk in zip(
        featurized, preprocessed, strict=True
    ):
        if featurized_chunk.num_rows != preprocessed_chunk.num_rows:
            raise ValueError("featurized and preprocessed chunks differ in row count")
        yield featurized_chunk, preprocessed_chunk


def select_aligned(
    featurized: pa.Table,
    preprocessed: pa.Table,
    local_positions: np.ndarray,
    id_column: str,
) -> pa.Table:
    indices = pa.array(local_positions, type=pa.int64())
    selected_featurized = featurized.take(indices)
    selected_preprocessed = preprocessed.take(indices)
    if not selected_featurized[id_column].equals(selected_preprocessed[id_column]):
        raise ValueError(f"Misaligned inputs: '{id_column}' differs between sides")
    return selected_featurized.append_column(
        CONFORMER_COLUMN, selected_preprocessed[CONFORMER_COLUMN]
    )


def write_aligned_selection(
    featurized_files: list[str],
    preprocessed_files: list[str],
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
        for featurized, preprocessed in aligned_chunks(
            featurized_files, preprocessed_files, id_column, batch_size
        ):
            end = offset + featurized.num_rows
            lo, hi = np.searchsorted(positions, [offset, end])
            selected = select_aligned(
                featurized, preprocessed, positions[lo:hi] - offset, id_column
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
