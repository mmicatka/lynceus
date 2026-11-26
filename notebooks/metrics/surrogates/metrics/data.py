# notebooks/metrics/surrogates/metrics/data.py

import re
from pathlib import Path

import numpy as np
import polars as pl
from metrics.common import ValidationSet

ROUND_PATTERN = re.compile(r"round_(\d+)\.model\.joblib$")
POSITIONAL_NAME = re.compile(r"Column_\d+")


def load_validation(directory: Path) -> ValidationSet:
    labels_path = directory / "docking.results.parquet"
    cleaned = load_and_clean_data(
        pl.read_parquet(directory / "features.parquet"),
        pl.read_parquet(labels_path),
    )
    threshold = get_validation_threshold(str(labels_path))
    labels = np.asarray(
        compute_labels(cleaned["affinity_kcal_mol"], threshold=threshold)
    )
    return ValidationSet(cleaned=cleaned, labels=labels, threshold=threshold)


def discover_models(models_dir: Path) -> dict[int, Path]:
    found = {
        int(match.group(1)): path
        for path in models_dir.glob("round_*.model.joblib")
        if (match := ROUND_PATTERN.search(path.name))
    }
    if not found:
        raise FileNotFoundError(f"no round_*.model.joblib files in {models_dir}")
    return dict(sorted(found.items()))


def resolve_feature_columns(
    model,
    features: pl.DataFrame,
    id_column: str = "id",
    feature_columns: list[str] | None = None,
) -> list[str]:
    names = list(model.feature_name_)
    if not all(POSITIONAL_NAME.fullmatch(name) for name in names):
        return names

    candidates = feature_columns or [c for c in features.columns if c != id_column]
    if len(candidates) != model.n_features_in_:
        raise ValueError(
            f"model expects {model.n_features_in_} features but {len(candidates)} "
            "candidate columns are available; pass feature_columns explicitly"
        )
    return candidates
