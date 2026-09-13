# modules/local/generate_conformers/src/generate_conformers/cli.py

import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.cli import NumWorkers
from lynceus_utils.duckdb import get_connection

from generate_conformers.generate_conformers import generate_conformers_chunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class ShardWriter:
    def __init__(self, output_dir: Path, rows_per_shard: int):
        self._output_dir = output_dir
        self._rows_per_shard = rows_per_shard
        self._shard_idx = 0
        self._shard_rows = 0
        self._open_shard: tuple[pq.ParquetWriter, Path, Path] | None = None

    def write(self, batch: pa.RecordBatch) -> None:
        if self._open_shard is None:
            self._open_shard = self._start_shard(batch.schema)

        writer, _, _ = self._open_shard
        writer.write_batch(batch)
        self._shard_rows += batch.num_rows

        if self._shard_rows >= self._rows_per_shard:
            self._close_shard()

    def _start_shard(self, schema: pa.Schema) -> tuple[pq.ParquetWriter, Path, Path]:
        final_path = self._output_dir / f"shard_{self._shard_idx:04d}.parquet"
        tmp_path = final_path.with_suffix(".parquet.tmp")
        writer = pq.ParquetWriter(tmp_path, schema)
        self._shard_rows = 0
        return writer, tmp_path, final_path

    def _close_shard(self) -> None:
        if self._open_shard is None:
            return

        writer, tmp_path, final_path = self._open_shard
        writer.close()
        os.replace(tmp_path, final_path)
        self._open_shard = None
        self._shard_idx += 1

    def close(self) -> None:
        self._close_shard()


@click.command()
@click.option("--input", type=str, required=True, help="Path to the input file.")
@click.option("--output", type=str, required=True, help="Output Parquet file.")
@click.option("--batch-size", default=1_000, type=int, help="DuckDB read batch size.")
@click.option(
    "--chunk-size",
    default=50,
    type=int,
    help="Worker chunk size for the conformer process pool.",
)
@click.option("--rows-per-shard", default=1_000_000, type=int, help="Rows per shard.")
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def generate_conformers(
    input: str,
    output: str,
    batch_size: int,
    chunk_size: int,
    rows_per_shard: int,
    num_workers: int,
):
    conn = get_connection()

    query_res = conn.execute(f"""
        SELECT
            column0 AS smiles,
            column1 AS zinc_id
        FROM read_csv('{input}', delim='\t', header=false)
    """)

    reader = query_res.to_arrow_reader(batch_size=batch_size)

    output_dir = Path(output)
    shard_writer = ShardWriter(output_dir, rows_per_shard)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for i, batch in enumerate(reader):
            smiles_list = batch["smiles"].to_pylist()

            conformers = generate_conformers_chunk(
                executor, smiles_list, chunk_size=chunk_size
            )

            new_batch = batch.append_column(
                "conformer", pa.array(conformers, type=pa.string())
            )

            shard_writer.write(new_batch)

            logger.info("processed %d", (i + 1) * batch_size)

    shard_writer.close()
