# notebooks/metrics/surrogates/metrics/score.py


from functools import partial
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np
import polars as pl
from skfp.metrics import bedroc_score, enrichment_factor
from sklearn.metrics import average_precision_score, roc_auc_score
from surrogate_model.common.data import flatten_features
from surrogate_model.common.metrics import predict_active

from notebooks.metrics.surrogates.metrics.common import Metric, ValidationSet
from notebooks.metrics.surrogates.metrics.data import resolve_feature_columns


def _fraction_label(fraction: float) -> str:
    return f"{fraction * 100:g}%"


def predict_scores(
    model,
    features: pl.DataFrame,
    id_column: str = "id",
    feature_columns: list[str] | None = None,
) -> np.ndarray:
    columns = resolve_feature_columns(model, features, id_column, feature_columns)
    missing = set(columns) - set(features.columns)
    if missing:
        raise KeyError(
            f"validation features missing model columns: {sorted(missing)[:5]}"
        )
    return model.predict_proba(features.select(columns).to_numpy())[:, 1]


def score_rounds(
    model_paths: Mapping[int, Path],
    validation: ValidationSet,
    features: list[str],
) -> dict[int, np.ndarray]:
    x = flatten_features(validation.cleaned, features)
    return {
        round_index: np.asarray(predict_active(model=joblib.load(path), x=x))
        for round_index, path in model_paths.items()
    }


def _ranking(y_score: np.ndarray) -> np.ndarray:
    return np.argsort(-y_score, kind="stable")


def _top_count(size: int, fraction: float) -> int:
    return max(1, int(np.ceil(fraction * size)))


def recall_at_fraction(
    y_true: np.ndarray, y_score: np.ndarray, fraction: float
) -> float:
    top = _ranking(y_score)[: _top_count(y_true.size, fraction)]
    return float(y_true[top].sum() / y_true.sum())


def precision_at_fraction(
    y_true: np.ndarray, y_score: np.ndarray, fraction: float
) -> float:
    top = _ranking(y_score)[: _top_count(y_true.size, fraction)]
    return float(y_true[top].mean())


def normalized_enrichment_factor(
    y_true: np.ndarray, y_score: np.ndarray, fraction: float
) -> float:
    max_ef = min(1 / fraction, y_true.size / y_true.sum())
    return float(enrichment_factor(y_true, y_score, fraction=fraction) / max_ef)


def fraction_for_recall(
    y_true: np.ndarray, y_score: np.ndarray, target: float
) -> float:
    cumulative = np.cumsum(y_true[_ranking(y_score)])
    index = np.searchsorted(cumulative, target * y_true.sum(), side="left")
    return float((index + 1) / y_true.size)


def build_metrics(
    fractions: tuple[float, ...] = (0.001, 0.01, 0.05, 0.1),
    recall_targets: tuple[float, ...] = (0.5, 0.9),
    bedroc_alpha: float = 20.0,
) -> dict[str, Metric]:
    metrics: dict[str, Metric] = {
        "roc_auc": roc_auc_score,
        "average_precision": average_precision_score,
        f"bedroc_{bedroc_alpha:g}": partial(bedroc_score, alpha=bedroc_alpha),
    }
    for fraction in fractions:
        label = _fraction_label(fraction)
        metrics[f"ef@{label}"] = partial(enrichment_factor, fraction=fraction)
        metrics[f"nef@{label}"] = partial(
            normalized_enrichment_factor, fraction=fraction
        )
        metrics[f"recall@{label}"] = partial(recall_at_fraction, fraction=fraction)
        metrics[f"precision@{label}"] = partial(
            precision_at_fraction, fraction=fraction
        )
    for target in recall_targets:
        metrics[f"library_fraction_for_{target:.0%}_recall"] = partial(
            fraction_for_recall, target=target
        )
    return metrics


def compute_metrics(
    run: str,
    labels: np.ndarray,
    scores_by_round: Mapping[int, np.ndarray],
    metrics: Mapping[str, Metric],
) -> pl.DataFrame:
    rows = [
        {
            "run": run,
            "round": round_index,
            **{name: float(fn(labels, scores)) for name, fn in metrics.items()},
        }
        for round_index, scores in scores_by_round.items()
    ]
    return pl.DataFrame(rows)


def compute_gain_curves(
    run: str,
    labels: np.ndarray,
    scores_by_round: Mapping[int, np.ndarray],
    points: int = 500,
) -> pl.DataFrame:
    positions = np.unique(np.geomspace(1, labels.size, points).astype(int))
    frames = []
    for round_index, scores in scores_by_round.items():
        cumulative = np.cumsum(labels[_ranking(scores)])
        frames.append(
            pl.DataFrame(
                {
                    "run": run,
                    "round": round_index,
                    "fraction": positions / labels.size,
                    "recall": cumulative[positions - 1] / labels.sum(),
                }
            )
        )
    return pl.concat(frames)
