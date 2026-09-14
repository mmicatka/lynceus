# modules/local/rebalance_candidates/src/rebalance_candidates/shard.py

import heapq
import json
import logging
from dataclasses import dataclass

import click
import duckdb
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ShardAssignment(BaseModel):
    shard_id: int
    folder: str
    source_key: str
    row_start: int | None = None
    row_end: int | None = None
    full_file: bool = True


class ShardPlan(BaseModel):
    n_shards: int
    target_rows_per_shard: int
    assignments: list[ShardAssignment]


@dataclass
class FolderSampleFile:
    folder: str
    source_key: str
    row_count: int


def _collect_folder_files(
    conn: duckdb.DuckDBPyConnection, source_glob: str
) -> list[FolderSampleFile]:
    rows = conn.sql(
        f"""
        SELECT folder, filename, count(*) AS row_count
        FROM read_parquet('{source_glob}', filename=true)
        GROUP BY folder, filename
        """
    ).fetchall()

    if not rows:
        raise RuntimeError(f"No candidate sample files found at {source_glob}")

    return [
        FolderSampleFile(folder=folder, source_key=filename, row_count=row_count)
        for folder, filename, row_count in rows
    ]


def _write_manifest(
    manifest_key: str,
    manifest_rows: list[dict],
    use_blob_storage: bool,
    bucket: str,
) -> None:
    manifest_lines = [json.dumps(row) for row in manifest_rows]
    content = "\n".join(manifest_lines) + "\n"

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = (
        f"s3://{bucket}/{manifest_key.lstrip('/')}"
        if use_blob_storage
        else manifest_key
    )

    with fs.open(resolved_path, "w") as f:
        f.write(content)

    logger.info("Wrote shard manifest to %s", resolved_path)


def _plan_balanced_shards(
    files: list[FolderSampleFile],
    n_shards: int,
) -> ShardPlan:
    if n_shards <= 0:
        raise RuntimeError(f"n_shards must be positive, got {n_shards}")
    if not files:
        raise RuntimeError("No folder sample files provided for shard planning")

    total_rows = sum(f.row_count for f in files)
    target_rows_per_shard = total_rows // n_shards
    if target_rows_per_shard == 0:
        raise RuntimeError(
            f"target_rows_per_shard resolved to 0: total_rows={total_rows},"
            f" n_shards={n_shards}"
        )

    shard_heap = [(0, shard_id) for shard_id in range(n_shards)]
    heapq.heapify(shard_heap)

    assignments: list[ShardAssignment] = []
    files_sorted = sorted(files, key=lambda f: f.row_count, reverse=True)

    for file in files_sorted:
        if file.row_count <= target_rows_per_shard:
            current_load, shard_id = heapq.heappop(shard_heap)
            assignments.append(
                ShardAssignment(
                    shard_id=shard_id,
                    folder=file.folder,
                    source_key=file.source_key,
                    full_file=True,
                )
            )
            heapq.heappush(shard_heap, (current_load + file.row_count, shard_id))
            continue

        n_splits = max(1, math_ceil_div(file.row_count, target_rows_per_shard))
        rows_per_split = math_ceil_div(file.row_count, n_splits)

        for split_index in range(n_splits):
            row_start = split_index * rows_per_split
            row_end = min(row_start + rows_per_split, file.row_count)
            if row_start >= row_end:
                continue

            current_load, shard_id = heapq.heappop(shard_heap)
            assignments.append(
                ShardAssignment(
                    shard_id=shard_id,
                    folder=file.folder,
                    source_key=file.source_key,
                    row_start=row_start,
                    row_end=row_end,
                    full_file=False,
                )
            )
            heapq.heappush(shard_heap, (current_load + (row_end - row_start), shard_id))

    return ShardPlan(
        n_shards=n_shards,
        target_rows_per_shard=target_rows_per_shard,
        assignments=assignments,
    )


def math_ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise RuntimeError(f"denominator must be positive, got {denominator}")
    return numerator // denominator


def _read_existing_manifest(
    manifest_key: str, use_blob_storage: bool, bucket: str
) -> list[dict] | None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = (
        f"s3://{bucket}/{manifest_key.lstrip('/')}"
        if use_blob_storage
        else manifest_key
    )

    if not fs.exists(resolved_path):
        return None

    with fs.open(resolved_path, "r") as f:
        lines = f.read().splitlines()

    return [json.loads(line) for line in lines if line]


def _manifest_is_valid(
    manifest_rows: list[dict], n_shards: int, output: str, conn
) -> bool:
    if len(manifest_rows) != n_shards:
        return False

    expected_shard_ids = set(range(n_shards))
    manifest_shard_ids = {row.get("shard_id") for row in manifest_rows}
    if manifest_shard_ids != expected_shard_ids:
        return False

    for row in manifest_rows:
        expected_output_path = f"{output.rstrip('/')}/shard_{row['shard_id']}.parquet"
        if row.get("output_path") != expected_output_path:
            return False

        result = conn.read_parquet(expected_output_path).count("*").fetchone()
        if result is None or result[0] != row.get("row_count"):
            return False

    return True


@click.command()
@click.option(
    "--input",
    "input_glob",
    required=True,
    type=str,
    help="Glob pattern for candidate sample Parquet files.",
)
@click.option(
    "--n-shards",
    "n_shards",
    required=True,
    type=int,
    help="Number of balanced output shards to write.",
)
@click.option(
    "--output",
    required=True,
    type=str,
    help="Output folder for shard_{i}.parquet files.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read input and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def shard_candidate_samples(
    input_glob: str,
    n_shards: int,
    output: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    if n_shards <= 0:
        raise RuntimeError(f"n_shards must be positive, got {n_shards}")

    output_key = output.rstrip("/")

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        input_glob = f"s3://{bucket}/{input_glob.lstrip('/')}"
        output = f"s3://{bucket}/{output_key.lstrip('/')}"
    else:
        conn = get_connection()

    manifest_key = f"{output_key}/shard_manifest.jsonl"

    existing_manifest_rows = _read_existing_manifest(
        manifest_key, use_blob_storage, bucket
    )
    if existing_manifest_rows is not None and _manifest_is_valid(
        existing_manifest_rows, n_shards, output, conn
    ):
        logger.info(
            "%s already reflects %d valid shards, skipping",
            manifest_key,
            n_shards,
        )
        return

    files = _collect_folder_files(conn, input_glob)

    logger.info("Collected %d candidate sample files for shard planning", len(files))

    shard_plan = _plan_balanced_shards(files, n_shards)
    logger.info(
        "Shard plan: n_shards=%d target_rows_per_shard=%d assignments=%d",
        shard_plan.n_shards,
        shard_plan.target_rows_per_shard,
        len(shard_plan.assignments),
    )

    assignments_by_shard: dict[int, list] = {i: [] for i in range(n_shards)}
    for assignment in shard_plan.assignments:
        assignments_by_shard[assignment.shard_id].append(assignment)

    manifest_rows = []
    for shard_id, assignments in assignments_by_shard.items():
        if not assignments:
            raise RuntimeError(f"shard_id={shard_id} received zero assignments")

        output_path = f"{output.rstrip('/')}/shard_{shard_id}.parquet"

        union_parts = []
        for assignment in assignments:
            if assignment.full_file:
                union_parts.append(
                    f"SELECT * FROM read_parquet('{assignment.source_key}')"
                )
            else:
                union_parts.append(
                    f"""
                    SELECT * EXCLUDE (rn)
                    FROM (
                        SELECT *, row_number() OVER () - 1 AS rn
                        FROM read_parquet('{assignment.source_key}')
                    )
                    WHERE rn >= {assignment.row_start} AND rn < {assignment.row_end}
                    """
                )
        shard_rel = conn.sql(" UNION ALL ".join(union_parts))

        export_parquet(conn, shard_rel, output_path)

        row_count = conn.read_parquet(output_path).count("*").fetchone()
        if row_count is None or row_count[0] == 0:
            raise RuntimeError(
                f"shard_id={shard_id} produced empty output at {output_path}"
            )

        logger.info(
            "shard_id=%d wrote %d rows to %s", shard_id, row_count[0], output_path
        )
        manifest_rows.append(
            {
                "shard_id": shard_id,
                "output_path": output_path,
                "row_count": row_count[0],
            }
        )

    _write_manifest(manifest_key, manifest_rows, use_blob_storage, bucket)
