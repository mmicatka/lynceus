# notebooks/metrics/surrogates/metrics/common.py


from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import polars as pl

BEDROC_PREFIX = "BEDROC"

ScoresByRound = Mapping[int, np.ndarray]


@dataclass(frozen=True)
class ValidationSet:
    cleaned: pl.DataFrame
    labels: np.ndarray
    threshold: float


def fraction_label(fraction: float) -> str:
    return f"{fraction * 100:g}%"
