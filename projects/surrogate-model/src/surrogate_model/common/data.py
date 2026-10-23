# projects/surrogate-model/src/surrogate_model/common/data.py

from typing import Optional

import numpy as np
import polars as pl

AFFINITY_COLUMN_NAME = "affinity_kcal_mol"


def load_and_clean_data(
    features: pl.DataFrame, labels: Optional[pl.DataFrame] = None
) -> pl.DataFrame:
    df = features.filter(pl.all_horizontal(pl.col("^.*_valid$")))

    if labels is not None:
        df = df.join(labels, on="id")
        df = df.filter(pl.col(AFFINITY_COLUMN_NAME) < 0)

    return df


def flatten_features(df: pl.DataFrame, feature_cols=None) -> np.ndarray:
    if feature_cols is None:
        feature_cols = []

    feature_arrays = []

    for col in feature_cols:
        arr = df[col].to_numpy()

        if arr.ndim == 1 and hasattr(arr[0], "__len__"):
            arr = np.stack(arr)

        feature_arrays.append(arr)

    return np.hstack(feature_arrays)


def compute_labels(
    raw: pl.Series | np.ndarray, threshold: float
) -> tuple[np.ndarray, float]:
    if isinstance(raw, pl.Series):
        raw = raw.to_numpy()

    labels = (raw <= threshold).astype(int)

    return labels, threshold
