# projects/surrogate-model/src/surrogate_model/common/data.py


import numpy as np
import polars as pl

AFFINITY_COLUMN_NAME = "affinity_kcal_mol"


def load_and_clean_data(features: pl.DataFrame, labels: pl.DataFrame) -> pl.DataFrame:
    df = features.filter(pl.all_horizontal(pl.col("^.*_valid$")))
    df = df.unique(subset=["id"], keep="first")

    labels = labels.filter(pl.col(AFFINITY_COLUMN_NAME) < 0)
    labels = labels.unique(subset=["id"], keep="first")

    df_clean = df.join(labels, on="id", how="inner")

    return df_clean


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


def compute_labels(raw: pl.Series | np.ndarray, threshold: float) -> np.ndarray:
    if isinstance(raw, pl.Series):
        raw = raw.to_numpy()

    labels = (raw <= threshold).astype(int)

    return labels


def prepare_dataset(
    feature_paths: list[str],
    labels_paths: list[str],
    features: list[str],
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    raw_features = pl.read_parquet(feature_paths)
    raw_labels = pl.read_parquet(labels_paths)

    df_cleaned = load_and_clean_data(raw_features, raw_labels)

    x = flatten_features(df_cleaned, features)
    y_raw = df_cleaned["affinity_kcal_mol"]

    y_label = compute_labels(y_raw, threshold=threshold)

    return x, y_label
