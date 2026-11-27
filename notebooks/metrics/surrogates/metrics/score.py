# notebooks/metrics/surrogates/metrics/score.py


from collections.abc import Mapping, Sequence
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from scipy.stats import spearmanr
from surrogate_model.common.data import flatten_features
from surrogate_model.common.metrics import (
    DEFAULT_BEDROC_ALPHAS,
    DEFAULT_EVAL_PERCENTS,
    evaluation_metrics,
    predict_active,
)

from .common import BEDROC_PREFIX, ScoresByRound, ValidationSet

DEFAULT_CURVE_POINTS = 500
DEFAULT_TAIL_SPEARMAN_FRACTION = 0.01


def score_rounds(
    model_paths: Mapping[int, Path],
    validation: ValidationSet,
    features: Sequence[str],
) -> dict[int, np.ndarray]:
    x = flatten_features(validation.cleaned, list(features))
    return {
        round_index: predict_active(model=joblib.load(path), x=x)
        for round_index, path in model_paths.items()
    }


def _ranking(scores: np.ndarray) -> np.ndarray:
    return np.argsort(-scores, kind="stable")


def _safe_spearman(neg_affinities: np.ndarray, scores: np.ndarray) -> float:
    if (
        neg_affinities.size < 3
        or np.ptp(neg_affinities) == 0.0
        or np.ptp(scores) == 0.0
    ):
        return float("nan")
    corr, _ = spearmanr(neg_affinities, scores)
    return float(corr)


def _tail_spearman_metrics(
    labels: np.ndarray,
    scores: np.ndarray,
    affinities: np.ndarray,
    top_fraction: float = DEFAULT_TAIL_SPEARMAN_FRACTION,
) -> dict[str, float]:
    # Negate docking affinity so tighter binders (more negative energy) are larger,
    # matching the sign convention of `scores` (higher = more active).
    neg_affinity = -np.asarray(affinities, dtype=np.float64)
    active_mask = np.asarray(labels, dtype=bool)

    top_k = max(1, int(scores.size * top_fraction))
    top_idx = _ranking(scores)[:top_k]

    return {
        "spearman@active": _safe_spearman(
            neg_affinity[active_mask], scores[active_mask]
        ),
        f"spearman@{top_fraction * 100:g}%": _safe_spearman(
            neg_affinity[top_idx], scores[top_idx]
        ),
    }


def _round_row(
    run: str,
    round_index: int,
    table: pl.DataFrame,
    extra_metrics: Mapping[str, float] | None = None,
) -> dict[str, object]:
    records = table.to_dicts()
    row: dict[str, object] = {"run": run, "round": round_index}
    for record in records:
        label = f"{record['Top %']:g}%"
        row[f"recall@{label}"] = record["Recall"]
        row[f"ef@{label}"] = record["EF"]
    row.update({k: v for k, v in records[0].items() if k.startswith(BEDROC_PREFIX)})
    if extra_metrics:
        row.update(extra_metrics)
    return row


def compute_metrics(
    run: str,
    labels: np.ndarray,
    scores_by_round: ScoresByRound,
    percents: Sequence[float] = DEFAULT_EVAL_PERCENTS,
    bedroc_alphas: Sequence[float] = DEFAULT_BEDROC_ALPHAS,
    affinities: np.ndarray | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            _round_row(
                run,
                round_index,
                evaluation_metrics(
                    labels, scores, percents=percents, bedroc_alphas=bedroc_alphas
                ),
                extra_metrics=(
                    None
                    if affinities is None
                    else _tail_spearman_metrics(labels, scores, affinities)
                ),
            )
            for round_index, scores in scores_by_round.items()
        ]
    )


def compute_gain_curves(
    run: str,
    labels: np.ndarray,
    scores_by_round: ScoresByRound,
    points: int = DEFAULT_CURVE_POINTS,
) -> pl.DataFrame:
    positions = np.unique(np.geomspace(1, labels.size, points).astype(int))
    total_hits = labels.sum()
    return pl.concat(
        [
            pl.DataFrame(
                {
                    "run": run,
                    "round": round_index,
                    "fraction": positions / labels.size,
                    "recall": np.cumsum(labels[_ranking(scores)])[positions - 1]
                    / total_hits,
                }
            )
            for round_index, scores in scores_by_round.items()
        ]
    )
