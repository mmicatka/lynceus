# modules/local/sample_candidates/src/sample_candidates/binning.py

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from sample_candidates.config import StratificationConfig


@dataclass(frozen=True)
class QuantileBinner:
    dim_edges: tuple[tuple[float, ...], ...]
    n_projected_dims: int

    def __post_init__(self) -> None:
        if len(self.dim_edges) != self.n_projected_dims:
            raise ValueError(
                f"Expected edges for {self.n_projected_dims} dimensions, "
                f"got {len(self.dim_edges)}."
            )
        for i, edges in enumerate(self.dim_edges):
            if list(edges) != sorted(edges):
                raise ValueError(f"Bin edges for proj_dim_{i} are not monotonic.")

    def stratum_column_expr(self) -> str:
        bucket_exprs = []
        for i, edges in enumerate(self.dim_edges):
            bucket_exprs.append(f"{self._case_when_bucket(i, edges)} AS bucket_dim_{i}")
        return ",\n    ".join(bucket_exprs)

    @staticmethod
    def _case_when_bucket(dim_index: int, edges: tuple[float, ...]) -> str:
        column = f"proj_dim_{dim_index}"
        conditions = [
            f"WHEN {column} < {edge} THEN {bucket_idx}"
            for bucket_idx, edge in enumerate(edges)
        ]
        conditions_sql = "\n            ".join(conditions)
        return f"""CASE
            {conditions_sql}
            ELSE {len(edges)}
        END"""

    def stratum_id_expr(self) -> str:
        bucket_cols = ", ".join(f"bucket_dim_{i}" for i in range(self.n_projected_dims))
        return f"concat_ws('_', {bucket_cols}) AS stratum_id"


def fit_quantile_bins(
    parquet_glob: str,
    config: StratificationConfig,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> QuantileBinner:
    conn = connection if connection is not None else duckdb.connect()

    quantile_fracs = [
        i / config.n_quantiles_per_dim for i in range(1, config.n_quantiles_per_dim)
    ]

    dim_select = ", ".join(
        f"approx_quantile(proj_dim_{i}, {quantile_fracs}) AS edges_{i}"
        for i in range(config.n_projected_dims)
    )

    query = f"""
        SELECT {dim_select}
        FROM read_parquet('{parquet_glob}')
    """

    result = conn.execute(query).fetchone()
    if result is None:
        raise ValueError(
            f"No rows returned computing quantile edges from '{parquet_glob}'; "
            "check the glob pattern and that projection has already run."
        )

    dim_edges = tuple(tuple(edges) for edges in result)

    return QuantileBinner(dim_edges=dim_edges, n_projected_dims=config.n_projected_dims)
