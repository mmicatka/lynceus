# modules/local/rebalance_candidates/src/rebalance_candidates/shard.py

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import click
import duckdb
from lynceus_utils.cli import NumWorkers
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
    rows_per_shard: int
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
    rows_per_shard: int,
) -> ShardPlan:
    if rows_per_shard <= 0:
        raise RuntimeError(f"rows_per_shard must be positive, got {rows_per_shard}")
    if not files:
        raise RuntimeError("No folder sample files provided for shard planning")

    assignments: list[ShardAssignment] = []
    current_shard_id = 0
    current_shard_rows = 0

    for file in files:
        remaining_file_rows = file.row_count
        current_row_start = 0

        while remaining_file_rows > 0:
            available_in_shard = rows_per_shard - current_shard_rows

            if available_in_shard == 0:
                current_shard_id += 1
                current_shard_rows = 0
                available_in_shard = rows_per_shard

            take_rows = min(remaining_file_rows, available_in_shard)
            is_full_file = take_rows == file.row_count

            assignments.append(
                ShardAssignment(
                    shard_id=current_shard_id,
                    folder=file.folder,
                    source_key=file.source_key,
                    row_start=current_row_start if not is_full_file else None,
                    row_end=(current_row_start + take_rows)
                    if not is_full_file
                    else None,
                    full_file=is_full_file,
                )
            )

            current_row_start += take_rows
            remaining_file_rows -= take_rows
            current_shard_rows += take_rows

    n_shards = current_shard_id + 1 if assignments else 0

    return ShardPlan(
        n_shards=n_shards,
        rows_per_shard=rows_per_shard,
        assignments=assignments,
    )


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
    manifest_rows: list[dict],
    rows_per_shard: int,
    output: str,
    conn: duckdb.DuckDBPyConnection,
) -> bool:
    if not manifest_rows:
        return False

    n_shards = len(manifest_rows)
    expected_shard_ids = set(range(n_shards))
    manifest_shard_ids = {row.get("shard_id") for row in manifest_rows}
    if manifest_shard_ids != expected_shard_ids:
        return False

    for row in manifest_rows:
        if row.get("row_count", 0) > rows_per_shard:
            return False

        expected_output_path = f"{output.rstrip('/')}/shard_{row['shard_id']}.parquet"
        if row.get("output_path") != expected_output_path:
            return False

        result = conn.read_parquet(expected_output_path).count("*").fetchone()
        if result is None or result[0] != row.get("row_count"):
            return False

    return True


def _write_shard(
    shard_id: int,
    assignments: list[ShardAssignment],
    output_path: str,
    use_blob_storage: bool,
) -> dict:
    """Worker function to process and write a single shard."""
    # Re-initialize the connection per-process, constraining internal threads to prevent CPU thrashing
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    conn = get_connection(blob_storage_settings, threads=2)

    union_parts = []
    for assignment in assignments:
        if assignment.full_file:
            union_parts.append(f"SELECT * FROM read_parquet('{assignment.source_key}')")
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

    return {
        "shard_id": shard_id,
        "output_path": output_path,
        "row_count": row_count[0],
    }


@click.command()
@click.option(
    "--input",
    "input_glob",
    required=True,
    type=str,
    help="Glob pattern for candidate sample Parquet files.",
)
@click.option(
    "--candidates-per-shard",
    "candidates_per_shard",
    required=True,
    type=click.IntRange(min=1),
    help="Maximum number of candidates per output shard.",
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
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def shard_candidate_samples(
    input_glob: str,
    candidates_per_shard: int,
    output: str,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
) -> None:
    output_key = output.rstrip("/")

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings, threads=num_workers)
        input_glob = f"s3://{bucket}/{input_glob.lstrip('/')}"
        output = f"s3://{bucket}/{output_key.lstrip('/')}"
    else:
        conn = get_connection(threads=num_workers)

    manifest_key = f"{output_key}/shard_manifest.jsonl"

    existing_manifest_rows = _read_existing_manifest(
        manifest_key, use_blob_storage, bucket
    )
    if existing_manifest_rows is not None and _manifest_is_valid(
        existing_manifest_rows, candidates_per_shard, output, conn
    ):
        logger.info(
            "%s already reflects valid shards under the %d"
            " rows-per-shard limit, skipping",
            manifest_key,
            candidates_per_shard,
        )
        return

    files = _collect_folder_files(conn, input_glob)

    logger.info("Collected %d candidate sample files for shard planning", len(files))

    shard_plan = _plan_balanced_shards(files, candidates_per_shard)
    logger.info(
        "Shard plan: n_shards=%d rows_per_shard=%d assignments=%d",
        shard_plan.n_shards,
        shard_plan.rows_per_shard,
        len(shard_plan.assignments),
    )

    assignments_by_shard: dict[int, list] = {i: [] for i in range(shard_plan.n_shards)}
    for assignment in shard_plan.assignments:
        assignments_by_shard[assignment.shard_id].append(assignment)

    manifest_rows = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {}
        for shard_id, assignments in assignments_by_shard.items():
            if not assignments:
                raise RuntimeError(f"shard_id={shard_id} received zero assignments")

            output_path = f"{output.rstrip('/')}/shard_{shard_id}.parquet"

            futures[
                executor.submit(
                    _write_shard, shard_id, assignments, output_path, use_blob_storage
                )
            ] = shard_id

        for future in as_completed(futures):
            shard_id = futures[future]
            try:
                result = future.result()
                logger.info(
                    "shard_id=%d wrote %d rows to %s",
                    result["shard_id"],
                    result["row_count"],
                    result["output_path"],
                )
                manifest_rows.append(result)
            except Exception:
                logger.exception("Failed processing shard_id=%d", shard_id)
                raise

    manifest_rows.sort(key=lambda x: x["shard_id"])
    _write_manifest(manifest_key, manifest_rows, use_blob_storage, bucket)
