# modules/local/sample_candidates/src/sample_candidates/autotune.py

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class StratificationShape:
    n_projected_dims: int
    n_quantiles_per_dim: int
    n_strata: int


def suggest_stratification_shape(
    n_input_rows: int,
    target_total_samples: int,
    n_quantiles_per_dim: int = 10,
    desired_cap_per_stratum: int = 20,
    min_dims: int = 1,
    max_dims: int = 12,
) -> StratificationShape:
    if n_input_rows <= 0:
        raise ValueError(f"n_input_rows must be positive, got {n_input_rows}.")
    if target_total_samples <= 0:
        raise ValueError(
            f"target_total_samples must be positive, got {target_total_samples}."
        )
    if n_quantiles_per_dim < 2:
        raise ValueError(
            f"n_quantiles_per_dim must be >= 2, got {n_quantiles_per_dim}."
        )
    if desired_cap_per_stratum < 1:
        raise ValueError(
            f"desired_cap_per_stratum must be >= 1, got {desired_cap_per_stratum}."
        )

    n_strata_target = max(target_total_samples / desired_cap_per_stratum, 1.0)
    raw_dims = math.log(n_strata_target) / math.log(n_quantiles_per_dim)
    n_projected_dims = max(min_dims, min(max_dims, round(raw_dims)))
    n_strata = n_quantiles_per_dim**n_projected_dims

    return StratificationShape(
        n_projected_dims=n_projected_dims,
        n_quantiles_per_dim=n_quantiles_per_dim,
        n_strata=n_strata,
    )
