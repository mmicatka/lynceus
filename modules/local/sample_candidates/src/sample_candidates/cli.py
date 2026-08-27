# modules/local/sample_candidates/src/sample_candidates/cli.py

import logging
from pathlib import Path

import click
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=True, path_type=Path),
    required=True,
    help="Path to an input file or directory containing parquet files.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to save the output single parquet file.",
)
@click.option(
    "--strata-col",
    type=str,
    required=True,
    help="Column name to perform stratified sampling on.",
)
@click.option(
    "--sample-size",
    type=int,
    required=True,
    help="Total target sample size across all strata.",
)
@click.option(
    "--num-strata",
    default=5,
    type=int,
    show_default=True,
    help="Number of quantile strata bins to construct using approx_quantile.",
)
@click.option("--seed", default=1000, type=int, show_default=True, help="Random seed.")
def sample_candidates(
    input_path: Path,
    output_path: Path,
    strata_col: str,
    sample_size: int,
    num_strata: int,
    seed: int,
):
    input_pattern = (
        str(input_path / "*.parquet") if input_path.is_dir() else str(input_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    probs = [round(i / num_strata, 4) for i in range(1, num_strata)]

    con = duckdb.connect()

    normalized_seed = (seed % 1000000) / 1000000.0
    con.execute(f"SELECT setseed({normalized_seed});")

    logger.info(f"Processing input files from: {input_pattern}")

    cutoffs = con.execute(
        """
    SELECT approx_quantile("topological_polar_surface_area", [0.2, 0.4, 0.6, 0.8])
    FROM read_parquet(?)
    """,
        ["preprocessed.parquet"],
    ).fetchone()[0]

    print("cutoffs:", cutoffs)

    strata_counts = con.execute(
        """
        SELECT
            len(list_filter(?, x -> x <= "topological_polar_surface_area")) AS stratum,
            count(*) AS n
        FROM read_parquet(?)
        GROUP BY stratum
        ORDER BY stratum
        """,
        [cutoffs, "preprocessed.parquet"],
    ).fetchall()

    print("input stratum counts:", strata_counts)

    query = f"""
        COPY (
            WITH quantile_bounds AS (
                SELECT approx_quantile("{strata_col}", {probs}) AS cutoffs
                FROM read_parquet('{input_pattern}')
            ),
            strata_assigned AS (
                SELECT
                    p.*,
                    CASE
                        WHEN p."{strata_col}" IS NULL THEN -1
                        ELSE len(list_filter(q.cutoffs, x -> x <= p."{strata_col}"))
                    END AS stratum
                FROM read_parquet('{input_pattern}') AS p
                CROSS JOIN quantile_bounds AS q
            ),
            strata_ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (PARTITION BY stratum ORDER BY random()) AS rn
                FROM strata_assigned
            )
            SELECT * EXCLUDE (stratum, rn)
            FROM strata_ranked
            WHERE rn <= ({sample_size} / {num_strata})
        ) TO '{output_path}' (FORMAT PARQUET);
        """

    logger.info("Executing DuckDB stratified sampling...")
    con.execute(query)
    logger.info(f"Sample written to: {output_path}")
