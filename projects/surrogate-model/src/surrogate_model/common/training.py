# projects/surrogate-model/src/surrogate_model/common/training.py


import time
from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl
from lynceus_core.logging import get_lynceus_logger
from sklearn.model_selection import train_test_split

from surrogate_model.common.data import prepare_dataset
from surrogate_model.common.metrics import (
    DEFAULT_EVAL_PERCENTS,
    evaluation_metrics,
    predict_active,
)
from surrogate_model.common.model import (
    DEFAULT_MODEL_TYPE,
    ModelType,
    ProbabilisticClassifier,
    TrainableClassifier,
    build_model,
)

logger = get_lynceus_logger()


def evaluate_and_log(
    model: ProbabilisticClassifier[Any],
    x,
    y_true,
    dataset_name: str,
    eval_percents: Sequence[float],
) -> pl.DataFrame:
    y_predict = predict_active(model=model, x=x)
    metrics = evaluation_metrics(y_true, y_predict, percents=eval_percents)
    logger.info(
        "Evaluation metrics generated", dataset_name=dataset_name, metrics=metrics
    )
    return metrics


def _metrics_records(metrics: pl.DataFrame | list[dict]) -> list[dict]:
    return metrics.to_dicts() if isinstance(metrics, pl.DataFrame) else metrics


def train_and_evaluate(
    train_features_paths: list[str],
    train_labels_paths: list[str],
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    threshold: float,
    random_seed: int,
    model_type: ModelType = DEFAULT_MODEL_TYPE,
    eval_percents: Sequence[float] = DEFAULT_EVAL_PERCENTS,
) -> tuple[TrainableClassifier[Any], dict]:
    x_initial, y_initial_label = prepare_dataset(
        train_features_paths,
        train_labels_paths,
        features,
        threshold=threshold,
    )

    logger.info("dataset", label_bins=np.bincount(y_initial_label))

    x_train, x_test, y_train, y_test = train_test_split(
        x_initial, y_initial_label, train_size=0.8, random_state=random_seed
    )

    model = build_model(model_type, random_state=random_seed)

    fit_start_time = time.perf_counter()
    model.fit(x_train, y_train)

    logger.info(
        "Trained model",
        model_type=str(model_type),
        samples=len(x_train),
        duration_seconds=round(time.perf_counter() - fit_start_time, 3),
    )

    evaluate_and_log(
        model,
        x_test,
        y_test,
        dataset_name="Initial Split",
        eval_percents=eval_percents,
    )

    x_validation, y_validation_label = prepare_dataset(
        [validation_features_path],
        [validation_labels_path],
        features,
        threshold=threshold,
    )

    validation_metrics = evaluate_and_log(
        model,
        x_validation,
        y_validation_label,
        dataset_name="Validation",
        eval_percents=eval_percents,
    )

    results = {
        "num_train_samples": len(x_train),
        "metrics": _metrics_records(validation_metrics),
    }
    return model, results
