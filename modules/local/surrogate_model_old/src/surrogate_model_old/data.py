# modules/local/surrogate/src/surrogate_model/data.py


from typing import Optional

import numpy as np
import polars as pl


def load_and_clean_data(
    features: pl.DataFrame, labels: Optional[pl.DataFrame] = None
) -> pl.DataFrame:
    df = features.filter(pl.all_horizontal(pl.col("^.*_valid$")))

    if labels is not None:
        df = df.join(labels, on="id")
        df = df.filter(pl.col("affinity_kcal_mol") < 0)

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


def label(
    raw: pl.Series | np.ndarray,
    threshold: Optional[float] = None,
    percentile: Optional[float] = None,
) -> tuple[np.ndarray, float]:
    if isinstance(raw, pl.Series):
        raw = raw.to_numpy()

    if threshold is None:
        if percentile is None:
            raise ValueError("Either 'threshold' or 'percentile' must be provided.")
        threshold = float(np.percentile(raw, percentile))

    labels = (raw <= threshold).astype(int)

    return labels, threshold
