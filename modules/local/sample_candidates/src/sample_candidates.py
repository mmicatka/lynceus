# modules/local/sample_candidates/src/sample_candidates.py

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import duckdb
import polars as pl
from rdkit import RDLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sample_candidates")

# RDKit's C++ logger is noisy on malformed SMILES
RDLogger.DisableLog("rdApp.*")


def _build_reservoir(input_glob: str, reservoir_size: int, seed: int) -> pl.DataFrame:
    logger.info(
        "Initializing DuckDB reservoir sample (size=%d) across: %s",
        reservoir_size,
        input_glob,
    )

    # We use a context manager to ensure the in-memory connection safely closes
    with duckdb.connect() as con:
        # Construct the sampling query using DuckDB's native reservoir algorithm
        # REPEATABLE(seed) ensures reproducibility across runs
        query = f"""
            SELECT *
            FROM read_parquet('{input_glob}')
            USING SAMPLE reservoir({reservoir_size} ROWS) REPEATABLE({seed});
        """

        # Execute the query and instantly materialize it as a Polars DataFrame
        res_df = con.execute(query).pl()

        logger.info(
            "DuckDB sampling complete. Materialized %d rows in %f.", res_df.height
        )
        return res_df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-glob",
        required=True,
        help="Glob pattern for batched candidate Parquet files, "
        'e.g. "candidates/batch_*.parquet"',
    )
    parser.add_argument(
        "--reservoir-size",
        type=int,
        default=25_000,
        help="Size of the intermediate uniform pool pulled from the stream.",
    )
    parser.add_argument("--output", required=True, help="Output Parquet path.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        reservoir_df = _build_reservoir(
            input_glob=args.input_glob,
            reservoir_size=args.reservoir_size,
            seed=args.seed,
        )
    except Exception as e:
        logger.error("DuckDB sampling failed: %s", e)
        return 1

    if reservoir_df.is_empty():
        logger.error(
            "Reservoir is empty - check your --input-glob pattern or file contents."
        )
        return 1

    # TODO: Add diversity sampling here
    out_df = reservoir_df

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    out_df.write_parquet(args.output)
    logger.info("Wrote %d candidates -> %s", out_df.height, args.output)


if __name__ == "__main__":
    main()
