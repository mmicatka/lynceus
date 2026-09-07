# modules/local/sample_candidates/src/sample_candidates/batch_projection.py

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

from sample_candidates.projection import ProjectionModel, _project_batch_worker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchProjectionResult:
    output_path: str
    n_rows: int
    n_batches: int


def _iter_record_batches(input_path: str, batch_size: int) -> Iterator[pa.RecordBatch]:
    parquet_file = pq.ParquetFile(input_path)
    yield from parquet_file.iter_batches(batch_size=batch_size)


def _default_n_workers() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count - 1)


def project_all_batches(
    input_path: str,
    output_path: str,
    model: ProjectionModel,
    batch_size: int = 50_000,
    n_workers: int | None = None,
) -> BatchProjectionResult:
    resolved_n_workers = n_workers if n_workers is not None else _default_n_workers()

    writer: pq.ParquetWriter | None = None
    n_rows = 0
    n_batches = 0

    try:
        with ProcessPoolExecutor(max_workers=resolved_n_workers) as executor:
            futures = {
                executor.submit(_project_batch_worker, batch, model): batch_index
                for batch_index, batch in enumerate(
                    _iter_record_batches(input_path, batch_size)
                )
            }

            if not futures:
                raise ValueError(
                    f"'{input_path}' produced no record batches to project."
                )

            results_by_index: dict[int, pa.RecordBatch] = {}
            for future in as_completed(futures):
                batch_index = futures[future]
                results_by_index[batch_index] = future.result()

            for batch_index in sorted(results_by_index):
                projected_batch = results_by_index[batch_index]
                if writer is None:
                    writer = pq.ParquetWriter(output_path, projected_batch.schema)
                writer.write_batch(projected_batch)
                n_rows += projected_batch.num_rows
                n_batches += 1
    finally:
        if writer is not None:
            writer.close()

    logger.info(
        "Projected %d rows across %d batches (%d workers) -> %s",
        n_rows,
        n_batches,
        resolved_n_workers,
        output_path,
    )

    return BatchProjectionResult(
        output_path=output_path, n_rows=n_rows, n_batches=n_batches
    )
