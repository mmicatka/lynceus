# notebooks/metrics/surrogates/metrics/score.py


from collections.abc import Mapping, Sequence
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from surrogate_model.common.data import flatten_features
from surrogate_model.common.metrics import (
    DEFAULT_BEDROC_ALPHAS,
    DEFAULT_EVAL_PERCENTS,
    evaluation_metrics,
    predict_active,
)

from .common import BEDROC_PREFIX, ScoresByRound, ValidationSet

DEFAULT_CURVE_POINTS = 500


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


def _round_row(run: str, round_index: int, table: pl.DataFrame) -> dict[str, object]:
    records = table.to_dicts()
    row: dict[str, object] = {"run": run, "round": round_index}
    for record in records:
        label = f"{record['Top %']:g}%"
        row[f"recall@{label}"] = record["Recall"]
        row[f"ef@{label}"] = record["EF"]
    row.update({k: v for k, v in records[0].items() if k.startswith(BEDROC_PREFIX)})
    return row


def compute_metrics(
    run: str,
    labels: np.ndarray,
    scores_by_round: ScoresByRound,
    percents: Sequence[float] = DEFAULT_EVAL_PERCENTS,
    bedroc_alphas: Sequence[float] = DEFAULT_BEDROC_ALPHAS,
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            _round_row(
                run,
                round_index,
                evaluation_metrics(
                    labels, scores, percents=percents, bedroc_alphas=bedroc_alphas
                ),
            )
            for round_index, scores in scores_by_round.items()
        ]
    )


def _ranking(scores: np.ndarray) -> np.ndarray:
    return np.argsort(-scores, kind="stable")


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
