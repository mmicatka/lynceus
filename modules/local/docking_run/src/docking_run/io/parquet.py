# modules/local/docking_run/src/docking_run/io/parquet.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Optional

import fsspec
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


def _write_batches(
    writer: pq.ParquetWriter,
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    conformational_state_id: str,
    site_id: str,
    batch_rows: int,
) -> int:
    row_count = 0
    for batch in iter_docking_result_batches(
        results_iter,
        conformational_state_id=conformational_state_id,
        site_id=site_id,
        batch_rows=batch_rows,
    ):
        writer.write_batch(batch)
        row_count += batch.num_rows

    if row_count == 0:
        # No poses at all (e.g. every ligand failed to dock): still emit
        # a valid, empty Parquet file matching the schema rather than
        # leaving no file or an unopened one.
        writer.write_batch(_rows_to_record_batch([]))

    return row_count


def _write_docking_results_parquet_local(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: Path,
    *,
    conformational_state_id: str,
    site_id: str,
    compression: str,
    batch_rows: int,
) -> int:
    """Stream results to a local `out_path`, atomically.

    Writes go to a temp path first and are renamed to `out_path` only
    once every batch has been written successfully. If `results_iter`
    raises partway through, the partial temp file is removed and the
    exception re-raised — `out_path` is left untouched, never a
    truncated file, on any failure.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    try:
        with pq.ParquetWriter(
            tmp_path, DOCKING_RESULTS_SCHEMA, compression=compression
        ) as writer:
            row_count = _write_batches(
                writer,
                results_iter,
                conformational_state_id=conformational_state_id,
                site_id=site_id,
                batch_rows=batch_rows,
            )
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    os.replace(tmp_path, out_path)
    return row_count


def _write_docking_results_parquet_remote(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: str,
    *,
    filesystem: fsspec.AbstractFileSystem,
    conformational_state_id: str,
    site_id: str,
    compression: str,
    batch_rows: int,
) -> int:
    """Stream results to `out_path` on `filesystem` (e.g. S3/Garage).

    `pq.ParquetWriter` buffers the file and only issues the underlying
    PUT on close, so a single write to `out_path` is already atomic at
    the object level — there is no local-disk-style partial-write window
    to guard against, and no temp-path/rename step is needed. If
    `results_iter` raises partway through, no object is ever written to
    `out_path`, since `close()` (and therefore the PUT) never runs.
    """
    with filesystem.open(out_path, "wb") as fh:
        with pq.ParquetWriter(
            fh, DOCKING_RESULTS_SCHEMA, compression=compression
        ) as writer:
            row_count = _write_batches(
                writer,
                results_iter,
                conformational_state_id=conformational_state_id,
                site_id=site_id,
                batch_rows=batch_rows,
            )

    return row_count


def write_docking_results_parquet(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: Path | str,
    *,
    conformational_state_id: str,
    site_id: str,
    compression: str = "zstd",
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
    filesystem: Optional[fsspec.AbstractFileSystem] = None,
) -> int:
    """Stream docking results to `out_path` as a single Parquet file.

    `results_iter` yields (ligand_id, results) pairs — typically a
    DockingProvider.dock_batch() generator, consumed incrementally rather
    than materialized up front. Rows are flattened and written in
    `batch_rows`-sized RecordBatches via a single open ParquetWriter, so
    peak memory during the write is bounded by `batch_rows` rather than
    the total pose count.

    When `filesystem` is None, `out_path` is treated as a local path and
    written atomically via a temp-path-and-rename. When `filesystem` is
    provided (e.g. from `lynceus_utils.storage.filesystem.get_filesystem`
    for S3/Garage), `out_path` is treated as a key on that filesystem and
    written directly, since the underlying PUT is already atomic.

    Returns the total number of pose-rows written.
    """
    if filesystem is None:
        return _write_docking_results_parquet_local(
            results_iter,
            Path(out_path),
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            compression=compression,
            batch_rows=batch_rows,
        )
    else:
        return _write_docking_results_parquet_remote(
            results_iter,
            str(out_path),
            filesystem=filesystem,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            compression=compression,
            batch_rows=batch_rows,
        )
