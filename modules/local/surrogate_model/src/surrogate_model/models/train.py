# modules/local/surrogate_model/src/surrogate_model/models/train.py


from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split

from modules.local.surrogate_model.src.surrogate_model.models.registry import (
    ModelBundle,
)

logger = logging.getLogger(__name__)

# Docking engines whose score this surrogate might be trained to approximate.
# Kept as an open set of known strings rather than a closed enum: new engines
# (e.g. a future GPU fork) should be addable without a code change elsewhere,
# but "unknown"/typos should still be visible rather than silently accepted as
# equivalent to a real engine, so this is used for CLI choices, not validation.
KNOWN_SCORE_SOURCES = ("vina", "vina-gpu", "ad4", "other")

# Registry of available estimators. Extend this to add algorithms; the CLI and
# TrainConfig surface keys from here rather than a hardcoded enum.
ESTIMATORS: dict[str, type[BaseEstimator]] = {
    "random_forest": RandomForestRegressor,
    "gradient_boosting": GradientBoostingRegressor,
}


@dataclass(frozen=True)
class TrainConfig:
    target_column: str
    score_source: str
    id_column: str | None = None
    estimator_name: str = "random_forest"
    estimator_params: dict[str, Any] = field(default_factory=dict)
    test_size: float = 0.2
    cv_folds: int = 5
    random_state: int = 42


@dataclass
class TrainResult:
    bundle: ModelBundle
    metrics: dict[str, float]
    cv_scores: list[float]


def train(df: pl.DataFrame, config: TrainConfig) -> TrainResult:
    """Fit a regressor on a featurized dataframe and evaluate on a held-out split.

    ``df`` must already be featurized (e.g. via featurize_dataframe) and contain
    ``config.target_column`` holding docking scores from ``config.score_source``.
    Rows with a null target are dropped before training.
    """
    if config.target_column not in df.columns:
        raise KeyError(f"target_column {config.target_column!r} not found in dataframe")

    try:
        estimator_cls = ESTIMATORS[config.estimator_name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown estimator {config.estimator_name!r}. Available: {list(ESTIMATORS)}"
        ) from exc

    working = df.dropna(subset=[config.target_column])
    n_dropped = len(df) - len(working)
    if n_dropped:
        logger.warning("Dropped %d row(s) with null target before training", n_dropped)

    feature_spec = infer_feature_spec(
        working, id_column=config.id_column, extra_exclude=(config.target_column,)
    )
    X = build_feature_matrix(working, feature_spec)
    y = working[config.target_column].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.test_size, random_state=config.random_state
    )

    estimator = estimator_cls(
        random_state=config.random_state, **config.estimator_params
    )
    estimator.fit(X_train, y_train)

    metrics = _evaluate(estimator, X_test, y_test)

    cv_scores = cross_val_score(
        estimator_cls(random_state=config.random_state, **config.estimator_params),
        X,
        y,
        cv=config.cv_folds,
        scoring="r2",
    ).tolist()

    bundle = ModelBundle(
        estimator=estimator,
        feature_spec=feature_spec,
        metadata={
            "task": "regression",
            "score_source": config.score_source,
            "score_units": "kcal/mol",
            "score_semantics": "predicted docking score (binding free energy estimate), "
            "not a measured/experimental binding affinity",
            "estimator_name": config.estimator_name,
            "estimator_params": config.estimator_params,
            "target_column": config.target_column,
            "n_train_samples": len(X_train),
            "n_test_samples": len(X_test),
            "n_features": feature_spec.n_features,
            "metrics": metrics,
            "cv_scoring": "r2",
            "cv_scores": cv_scores,
        },
    )

    return TrainResult(bundle=bundle, metrics=metrics, cv_scores=cv_scores)


def _evaluate(
    estimator: BaseEstimator, X_test: np.ndarray, y_test: np.ndarray
) -> dict[str, float]:
    pred = estimator.predict(X_test)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
        "mae": float(mean_absolute_error(y_test, pred)),
        "r2": float(r2_score(y_test, pred)),
    }
