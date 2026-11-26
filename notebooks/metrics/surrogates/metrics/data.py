# notebooks/metrics/surrogates/metrics/data.py


import re
from pathlib import Path

import polars as pl
from surrogate_model.common.data import (
    AFFINITY_COLUMN_NAME,
    compute_labels,
    load_and_clean_data,
)
from surrogate_model.common.threshold import get_validation_threshold

from .common import ValidationSet

FEATURES_FILE = "features.parquet"
DOCKING_FILE = "docking.results.parquet"
ROUND_PATTERN = re.compile(r"round_(\d+)\.model\.joblib")


def load_validation(directory: Path) -> ValidationSet:
    docking_path = directory / DOCKING_FILE
    cleaned = load_and_clean_data(
        pl.read_parquet(directory / FEATURES_FILE),
        pl.read_parquet(docking_path),
    )
    threshold = get_validation_threshold(str(docking_path))
    labels = compute_labels(cleaned[AFFINITY_COLUMN_NAME], threshold=threshold)
    return ValidationSet(cleaned=cleaned, labels=labels, threshold=threshold)


def discover_models(models_dir: Path) -> dict[int, Path]:
    found = {
        int(match.group(1)): path
        for path in models_dir.iterdir()
        if (match := ROUND_PATTERN.fullmatch(path.name))
    }
    if not found:
        raise FileNotFoundError(f"no round_*.model.joblib files in {models_dir}")
    return dict(sorted(found.items()))
