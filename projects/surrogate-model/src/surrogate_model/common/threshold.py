# projects/surrogate-model/src/surrogate_model/common/threshold.py


import polars as pl
from lynceus_core.manifest.common import Manifest

from surrogate_model.common.data import AFFINITY_COLUMN_NAME


def _compute_active_threshold(
    validation_labels_path: str, active_percentile: float
) -> float:
    if not 0.0 < active_percentile <= 100.0:
        raise ValueError(
            f"active_percentile must be in (0, 100], got {active_percentile}."
        )

    affinities = (
        pl.scan_parquet(validation_labels_path)
        .select(pl.col(AFFINITY_COLUMN_NAME))
        .collect()
        .to_series()
    )
    negatives = affinities.filter(affinities < 0)

    if negatives.len() == 0:
        raise ValueError(
            f"No negative values found in column '{AFFINITY_COLUMN_NAME}'."
        )

    threshold = negatives.quantile(active_percentile / 100.0)

    if threshold is None:
        raise ValueError(f"Could not compute quantile for '{AFFINITY_COLUMN_NAME}'.")

    return threshold


def get_validation_threshold(
    validation_path: str, active_percentile: float = 1.0
) -> float:
    validation_manifest_path = f"{validation_path}.manifest.json"

    validation_manifest = Manifest(filepath=validation_manifest_path)

    if validation_manifest.exists():
        try:
            validation_manifest.load()
            if "threshold" in validation_manifest.data:
                return float(validation_manifest.data["threshold"])
        except Exception:
            pass

    threshold = _compute_active_threshold(validation_path, active_percentile)

    validation_manifest.data["threshold"] = threshold
    validation_manifest.save()

    return threshold
