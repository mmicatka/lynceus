# modules/local/sample_candidates/src/sample_candidates/sampling.py

from __future__ import annotations

import math

from sample_candidates.binning import QuantileBinner
from sample_candidates.config import StratificationConfig


def resolve_cap_per_stratum(config: StratificationConfig, n_strata: int) -> int:
    if config.cap_per_stratum is not None:
        return config.cap_per_stratum

    if config.target_total_samples is None:
        raise ValueError(
            "Neither cap_per_stratum nor target_total_samples is set; "
            "StratificationConfig validation should have prevented this."
        )
    if n_strata <= 0:
        raise ValueError(
            f"Cannot derive cap_per_stratum from target_total_samples with "
            f"n_strata={n_strata}."
        )
    return math.ceil(config.target_total_samples / n_strata)


def build_capped_sample_query(
    source_sql: str,
    binner: QuantileBinner,
    config: StratificationConfig,
    cap_per_stratum: int,
    row_id_expr: str = "row_number() OVER ()",
) -> str:
    bucket_columns = binner.stratum_column_expr()
    stratum_id = binner.stratum_id_expr()

    return f"""
        WITH source AS (
            SELECT *, {row_id_expr} AS __row_id
            FROM {source_sql}
        ),
        projected AS (
            SELECT __row_id,
    {bucket_columns}
            FROM source
        ),
        with_stratum AS (
            SELECT __row_id,
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
                w.__row_id,
                w.stratum_id,
                CASE
                    WHEN s.stratum_size < {config.min_stratum_size_for_cap}
                        THEN '__overflow__'
                    ELSE w.stratum_id
                END AS resolved_stratum_id
            FROM with_stratum w
            JOIN stratum_sizes s USING (stratum_id)
        ),
        ranked AS (
            SELECT
                __row_id,
                resolved_stratum_id,
                row_number() OVER (
                    PARTITION BY resolved_stratum_id
                    ORDER BY random()
                ) AS stratum_rank
            FROM resolved_stratum
            QUALIFY stratum_rank <= {cap_per_stratum}
        )
        SELECT source.* EXCLUDE (__row_id), ranked.resolved_stratum_id
        FROM source
        JOIN ranked ON source.__row_id = ranked.__row_id
    """
