# modules/local/docking_run/src/docking_run/output/parquet.py

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from docking_run.types.docking_result import DockingResult

# Default number of pose-rows buffered before flushing a RecordBatch to
# the Parquet writer. Bounds peak memory independent of how many ligands
# or poses-per-ligand a given invocation produces.
DEFAULT_STREAM_BATCH_ROWS = 10

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
    results_by_ligand: dict[str, list[DockingResult]],
    *,
    conformational_state_id: str,
    site_id: str,
) -> Iterator[tuple]:
    for catalog_id, results in results_by_ligand.items():
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
    results_by_ligand: dict[str, list[DockingResult]],
    *,
    conformational_state_id: str,
    site_id: str,
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
) -> Iterator[pa.RecordBatch]:
    if batch_rows <= 0:
        raise ValueError(f"batch_rows must be positive, got {batch_rows}")

    buffer: list[tuple] = []
    for row in _iter_pose_rows(
        results_by_ligand,
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
    results_by_ligand: dict[str, list[DockingResult]],
    *,
    conformational_state_id: str,
    site_id: str,
) -> pa.Table:
    batches = list(
        iter_docking_result_batches(
            results_by_ligand,
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
    results_by_ligand: dict[str, list[DockingResult]],
    out_path: Path,
    *,
    conformational_state_id: str,
    site_id: str,
    compression: str = "zstd",
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pq.ParquetWriter(
        out_path, DOCKING_RESULTS_SCHEMA, compression=compression
    ) as writer:
        wrote_any = False
        for batch in iter_docking_result_batches(
            results_by_ligand,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            batch_rows=batch_rows,
        ):
            writer.write_batch(batch)
            wrote_any = True

        if not wrote_any:
            # No poses at all (e.g. every ligand failed to dock): still
            # emit a valid, empty Parquet file matching the schema rather
            # than leaving no file or an unopened one.
            writer.write_batch(_rows_to_record_batch([]))
