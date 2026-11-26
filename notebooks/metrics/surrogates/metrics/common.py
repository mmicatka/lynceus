# notebooks/metrics/surrogates/metrics/common.py


from dataclasses import dataclass
from typing import Callable, SupportsFloat

import numpy as np
import polars as pl

Metric = Callable[[np.ndarray, np.ndarray], SupportsFloat]


@dataclass(frozen=True)
class LabelSpec:
    id_column: str = "id"
    score_column: str = "score"
    hit_fraction: float = 0.01
    threshold: float | None = None
    lower_is_better: bool = True


@dataclass(frozen=True)
class ValidationSet:
    cleaned: pl.DataFrame
    labels: np.ndarray
    threshold: float
