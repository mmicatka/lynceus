# modules/local/docking_run/src/docking_run/io/parquet.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from docking_run.types import DockingResult

# Default number of pose-rows buffered before flushing a RecordBatch to
# the Parquet writer. Bounds peak memory independent of how many ligands
# or poses-per-ligand a given invocation produces.
DEFAULT_STREAM_BATCH_ROWS = 10_000

# Explicit schema rather than inferred, so column types/nullability are
# stable across runs regardless of whether a given batch happens to
# contain nulls (e.g. rmsd_lb/rmsd_ub on a top pose).
DOCKING_RESULTS_SCHEMA = pa.schema(
    [
        pa.field("catalog_id", pa.string(), nullable=False),
        pa.field("conformational_state_id", pa.string(), nullable=False),
        pa.field("site_id", pa.string(), nullable=False),
        pa.field("mode", pa.int32(), nullable=False),
        pa.field("affinity_kcal_mol", pa.float64(), nullable=False),
        pa.field("rmsd_lb", pa.float64(), nullable=True),
        pa.field("rmsd_ub", pa.float64(), nullable=True),
        pa.field("pose_pdbqt", pa.string(), nullable=False),
    ]
)


def _iter_pose_rows(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    conformational_state_id: str,
    site_id: str,
) -> Iterator[tuple]:
    """Yield one flattened pose-row tuple at a time.

    `results_iter` yields (ligand_id, results) pairs — this is the same
    shape DockingProvider.dock_batch produces, so callers can pass a
    provider's generator straight through without materializing it into
    a dict first. A plain `dict[str, list[DockingResult]].items()` also
    satisfies this shape, for callers that already have one materialized.

    Row order matches DOCKING_RESULTS_SCHEMA field order:
    (catalog_id, conformational_state_id, site_id, mode,
    affinity_kcal_mol, rmsd_lb, rmsd_ub, pose_pdbqt).
    """
    for catalog_id, results in results_iter:
        for result in results:
            yield (
                catalog_id,
                conformational_state_id,
                site_id,
                result.mode,
                result.affinity_kcal_mol,
                result.rmsd_lb,
                result.rmsd_ub,
                str(result.pose_pdbqt),
            )


def _rows_to_record_batch(rows: list[tuple]) -> pa.RecordBatch:
    columns = list(zip(*rows)) if rows else [[] for _ in DOCKING_RESULTS_SCHEMA]
    arrays = [
        pa.array(column, type=field.type)
        for column, field in zip(columns, DOCKING_RESULTS_SCHEMA)
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=DOCKING_RESULTS_SCHEMA)


def iter_docking_result_batches(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    conformational_state_id: str,
    site_id: str,
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
) -> Iterator[pa.RecordBatch]:
    """Flatten and chunk docking results into fixed-size RecordBatches.

    `results_iter` is consumed incrementally (see `_iter_pose_rows`), and
    rows are buffered only `batch_rows` at a time rather than
    materializing every column for the full result set up front. This
    bounds peak memory during serialization independent of both total
    pose count and how eagerly `results_iter` itself was produced.
    """
    if batch_rows <= 0:
        raise ValueError(f"batch_rows must be positive, got {batch_rows}")

    buffer: list[tuple] = []
    for row in _iter_pose_rows(
        results_iter,
        conformational_state_id=conformational_state_id,
        site_id=site_id,
    ):
        buffer.append(row)
        if len(buffer) >= batch_rows:
            yield _rows_to_record_batch(buffer)
            buffer = []

    if buffer:
        yield _rows_to_record_batch(buffer)


def docking_results_to_table(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    conformational_state_id: str,
    site_id: str,
) -> pa.Table:
    """Flatten per-ligand docking results into a row-per-pose Arrow table.

    `conformational_state_id` and `site_id` are constant for a single
    docking_run invocation (one receptor conformer, one search box) and
    are broadcast onto every row so results from multiple runs can be
    concatenated downstream without losing that context.

    Materializes the full table in memory; prefer
    `write_docking_results_parquet` for large result sets, which streams
    instead.
    """
    batches = list(
        iter_docking_result_batches(
            results_iter,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
        )
    )
    if not batches:
        return pa.table(
            {field.name: [] for field in DOCKING_RESULTS_SCHEMA},
            schema=DOCKING_RESULTS_SCHEMA,
        )
    return pa.Table.from_batches(batches, schema=DOCKING_RESULTS_SCHEMA)


def write_docking_results_parquet(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: Path,
    *,
    conformational_state_id: str,
    site_id: str,
    compression: str = "zstd",
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
) -> None:
    """Stream docking results to `out_path` as a single Parquet file.

    `results_iter` yields (ligand_id, results) pairs — typically a
    DockingProvider.dock_batch() generator, consumed incrementally rather
    than materialized up front. Rows are flattened and written in
    `batch_rows`-sized RecordBatches via a single open ParquetWriter, so
    peak memory during the write is bounded by `batch_rows` rather than
    the total pose count.

    Writes go to a temp path first and are atomically renamed to
    `out_path` only once every batch has been written successfully. If
    `results_iter` raises partway through (e.g. a DockingError surfaced
    mid-docking by the provider), the partial temp file is removed and
    the exception re-raised — `out_path` is left untouched, never a
    truncated file, on any failure.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    try:
        with pq.ParquetWriter(
            tmp_path, DOCKING_RESULTS_SCHEMA, compression=compression
        ) as writer:
            wrote_any = False
            for batch in iter_docking_result_batches(
                results_iter,
                conformational_state_id=conformational_state_id,
                site_id=site_id,
                batch_rows=batch_rows,
            ):
                writer.write_batch(batch)
                wrote_any = True

            if not wrote_any:
                # No poses at all (e.g. every ligand failed to dock):
                # still emit a valid, empty Parquet file matching the
                # schema rather than leaving no file or an unopened one.
                writer.write_batch(_rows_to_record_batch([]))
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    os.replace(tmp_path, out_path)
