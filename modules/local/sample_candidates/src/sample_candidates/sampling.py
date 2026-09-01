# modules/local/sample_candidates/src/sample_candidates/sampling.py

from __future__ import annotations

from sample_candidates.binning import QuantileBinner
from sample_candidates.config import StratificationConfig


def build_capped_sample_query(
    parquet_glob: str,
    binner: QuantileBinner,
    config: StratificationConfig,
) -> str:
    bucket_columns = binner.stratum_column_expr()
    stratum_id = binner.stratum_id_expr()

    return f"""
        WITH projected AS (
            SELECT *,
    {bucket_columns}
            FROM read_parquet('{parquet_glob}')
        ),
        with_stratum AS (
            SELECT *,
                {stratum_id}
            FROM projected
        ),
        stratum_sizes AS (
            SELECT stratum_id, COUNT(*) AS stratum_size
            FROM with_stratum
            GROUP BY stratum_id
        ),
        resolved_stratum AS (
            SELECT
                w.*,
                CASE
                    WHEN s.stratum_size < {config.min_stratum_size_for_cap}
                        THEN '__overflow__'
                    ELSE w.stratum_id
                END AS resolved_stratum_id
            FROM with_stratum w
            JOIN stratum_sizes s USING (stratum_id)
        ),
        ranked AS (
            SELECT *,
                row_number() OVER (
                    PARTITION BY resolved_stratum_id
                    ORDER BY random()
                ) AS stratum_rank
            FROM resolved_stratum
        )
        SELECT *
        FROM ranked
        WHERE stratum_rank <= {config.cap_per_stratum}
    """
