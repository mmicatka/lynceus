# modules/local/docking_run/src/docking_run/io/parquet.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Optional

import duckdb
import pyarrow as pa

from docking_run.types import DockingResult

DEFAULT_STREAM_BATCH_ROWS = 10_000

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
    if batch_rows <= 0:
        raise ValueError(f"batch_rows must be positive, got {batch_rows}")

    buffer: list[tuple] = []
    n_batches_emitted = 0
    for row in _iter_pose_rows(
        results_iter,
        conformational_state_id=conformational_state_id,
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
    conformational_state_id: str,
    site_id: str,
) -> pa.Table:
    batches = list(
        iter_docking_result_batches(
            results_iter,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
        )
    )
    return pa.Table.from_batches(batches, schema=DOCKING_RESULTS_SCHEMA)


def _copy_reader_to_parquet(
    conn: duckdb.DuckDBPyConnection,
    reader: pa.RecordBatchReader,
    dest_path: str,
) -> int:
    conn.register("docking_results_reader", reader)
    try:
        conn.sql(
            f"COPY (SELECT * FROM docking_results_reader) "
            f"TO '{dest_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        res = conn.sql(
            "SELECT COUNT(*) FROM read_parquet($path)", params={"path": dest_path}
        ).fetchone()

        if res is None:
            raise RuntimeError(f"DuckDB query returned no relation for {dest_path}")
        return res[0]
    finally:
        conn.unregister("docking_results_reader")


def write_docking_results_parquet(
    results_iter: Iterable[tuple[str, list[DockingResult]]],
    out_path: Path | str,
    *,
    conformational_state_id: str,
    site_id: str,
    batch_rows: int = DEFAULT_STREAM_BATCH_ROWS,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    connection = conn or duckdb.connect()

    reader = pa.RecordBatchReader.from_batches(
        DOCKING_RESULTS_SCHEMA,
        iter_docking_result_batches(
            results_iter,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            batch_rows=batch_rows,
        ),
    )

    is_remote = "://" in str(out_path)

    if is_remote:
        return _copy_reader_to_parquet(connection, reader, str(out_path))

    local_path = Path(out_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")

    try:
        row_count = _copy_reader_to_parquet(connection, reader, str(tmp_path))
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    os.replace(tmp_path, local_path)
    return row_count
