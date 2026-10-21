# projects/lynceus-dock/src/lynceus_dock/common/results.py

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from lynceus_dock.common.types import DockingResult

DEFAULT_STREAM_BATCH_ROWS = 10_000
PARQUET_COMPRESSION = "zstd"
POSE_COLUMN = "pose_pdbqt"

DOCKING_RESULTS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("member_id", pa.string(), nullable=False),
        pa.field("site_id", pa.string(), nullable=False),
        pa.field("mode", pa.int32(), nullable=False),
        pa.field("affinity_kcal_mol", pa.float64(), nullable=False),
        pa.field("rmsd_lb", pa.float64(), nullable=True),
        pa.field("rmsd_ub", pa.float64(), nullable=True),
        pa.field(POSE_COLUMN, pa.string(), nullable=False),
    ]
)


def _output_schema(drop_pose_column: bool) -> pa.Schema:
    if not drop_pose_column:
        return DOCKING_RESULTS_SCHEMA
    return DOCKING_RESULTS_SCHEMA.remove(
        DOCKING_RESULTS_SCHEMA.get_field_index(POSE_COLUMN)
    )


def _iter_pose_rows(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    member_id: str,
    site_id: str,
) -> Iterator[tuple]:
    for ligand_id, results in results_iter:
        for result in results:
            yield (
                ligand_id,
                member_id,
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
    member_id: str,
    site_id: str,
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
) -> Iterator[pa.RecordBatch]:
    if batch_rows <= 0:
        raise ValueError(f"batch_rows must be positive, got {batch_rows}")

    buffer: list[tuple] = []
    n_batches_emitted = 0
    for row in _iter_pose_rows(
        results_iter,
        member_id=member_id,
        site_id=site_id,
    ):
        buffer.append(row)
        if len(buffer) >= batch_rows:
            yield _rows_to_record_batch(buffer)
            n_batches_emitted += 1
            buffer = []

    if buffer or n_batches_emitted == 0:
        yield _rows_to_record_batch(buffer)


def docking_results_to_table(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    *,
    member_id: str,
    site_id: str,
) -> pa.Table:
    batches = list(
        iter_docking_result_batches(
            results_iter,
            member_id=member_id,
            site_id=site_id,
        )
    )
    return pa.Table.from_batches(batches, schema=DOCKING_RESULTS_SCHEMA)


def _write_result_batches(
    batches: Iterable[pa.RecordBatch],
    dest_path: Path,
    schema: pa.Schema,
) -> int:
    row_count = 0
    with pq.ParquetWriter(dest_path, schema, compression=PARQUET_COMPRESSION) as writer:
        for batch in batches:
            writer.write_batch(batch.select(schema.names))
            row_count += batch.num_rows
    return row_count


def write_results(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: Path | str,
    *,
    member_id: str,
    site_id: str,
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
    drop_pose_column: bool = False,
) -> int:
    local_path = Path(out_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    batches = iter_docking_result_batches(
        results_iter,
        member_id=member_id,
        site_id=site_id,
        batch_rows=batch_rows,
    )

    row_count = _write_result_batches(
        batches, local_path, _output_schema(drop_pose_column)
    )

    return row_count
