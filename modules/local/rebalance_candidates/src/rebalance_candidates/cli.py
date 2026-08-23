import logging
from typing import Iterator, Sequence

import click
import pyarrow as pa
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _build_filtered_query(
    input_path: str, skip_col_vals: Sequence[tuple[str, str]]
) -> str:
    filter_conditions = [
        f"NOT COALESCE(LOWER(CAST({col} AS VARCHAR)) = '{val.lower()}', FALSE)"
        for col, val in skip_col_vals
    ]
    where_clause = (
        f"WHERE {' AND '.join(filter_conditions)}" if filter_conditions else ""
    )

    excluded_cols = list({col for col, _ in skip_col_vals})
    exclude_clause = f"EXCLUDE ({', '.join(excluded_cols)})" if excluded_cols else ""

    return f"""
        SELECT * {exclude_clause}
        FROM read_parquet('{input_path}')
        {where_clause}
    """


def _generate_sharded_tables(
    reader: pa.RecordBatchReader, num_per_shard: int
) -> Iterator[pa.Table]:
    current_batches: list[pa.RecordBatch] = []
    current_rows = 0

    for batch in reader:
        current_batches.append(batch)
        current_rows += batch.num_rows

        while current_rows >= num_per_shard:
            table = pa.Table.from_batches(current_batches)
            shard_table = table.slice(0, num_per_shard)
            remainder_table = table.slice(num_per_shard)

            yield shard_table

            if remainder_table.num_rows > 0:
                current_batches = remainder_table.to_batches()
                current_rows = remainder_table.num_rows
            else:
                current_batches = []
                current_rows = 0

    if current_rows > 0:
        yield pa.Table.from_batches(current_batches)


@click.command()
@click.option("--input-path", type=str, required=True, help="Input path.")
@click.option("--output-path", type=str, required=True, help="Output path.")
@click.option(
    "--num-per-shard",
    default=10000,
    type=int,
    show_default=True,
    help="Number of candidates per shard.",
)
@click.option(
    "--skip-col-val",
    type=(str, str),
    multiple=True,
    help="Column and value pair to skip (e.g. --skip-col-val steps_ok False)."
    " Can be passed multiple times.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output Parquet file to blob storage.",
)
@click.option("--bucket", type=str, default="lynceus", help="Output bucket name")
def rebalance_candidates(
    input_path: str,
    output_path: str,
    num_per_shard: int,
    skip_col_val: list[tuple[str, str]],
    use_blob_storage: bool,
    bucket: str,
):
    input_path = f"{input_path.rstrip('/')}/**/*.parquet"
    blob_storage_settings = None

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        target_dir = f"s3://{bucket}/{output_path.lstrip('/')}"
        input_path = f"s3://{bucket}/{input_path}"
    else:
        target_dir = output_path.rstrip("/")

    query = _build_filtered_query(input_path, skip_col_val)
    conn = get_connection(blob_storage_settings)

    logger.info(f"Reading from {input_path} with {num_per_shard} rows per file")

    reader = conn.execute(query).fetch_record_batch()

    shards_written = 0
    for shard_idx, shard_table in enumerate(
        _generate_sharded_tables(reader, num_per_shard)
    ):
        shard_file = f"{target_dir}/shard_{shard_idx}.parquet"
        export_parquet(conn, shard_table, shard_file)
        shards_written += 1

    logger.info(f"Successfully wrote {shards_written} shards to {output_path}")
