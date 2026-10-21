# projects/surrogate-model/src/surrogate_model/cli/train.py


import json
import os
import sys
import time
from typing import Optional

import click
import joblib
import lightgbm as lgb
import polars as pl
import structlog
from lynceus_core.features import FEATURE_COLS
from lynceus_core.logging import wide_log
from sklearn.model_selection import train_test_split

from surrogate_model.common.data import (
    compute_label,
    flatten_features,
    load_and_clean_data,
)
from surrogate_model.common.metrics import evaluation_metrics, predict_active


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()

RANDOM_SEED = 1000


def _marker_path(output_path: str) -> str:
    return f"{output_path}.SUCCESS"


def _model_is_valid(output_path: str, active_percentile: float) -> bool:
    marker_path = _marker_path(output_path)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        data = json.load(f)
        return data.get("active_percentile") == active_percentile


def _write_success_marker(output_path: str, active_percentile: float) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(_marker_path(output_path), "w") as f:
        json.dump({"active_percentile": active_percentile}, f)


def _prepare_dataset(
    features_path: str,
    labels_path: str,
    features: list[str],
    threshold: Optional[float] = None,
    percentile: Optional[float] = None,
) -> tuple:
    raw_features = pl.read_parquet(features_path)
    raw_labels = pl.read_parquet(labels_path)

    df_cleaned = load_and_clean_data(raw_features, raw_labels)

    x = flatten_features(df_cleaned, features)
    y_raw = df_cleaned["affinity_kcal_mol"]

    # "top" 1% (most negative == strongest binder) or use provided threshold
    y_label, computed_threshold = compute_label(
        y_raw, percentile=percentile, threshold=threshold
    )

    return x, y_label, computed_threshold


def _evaluate_and_log(model, x, y_true, dataset_name: str) -> pl.DataFrame:
    y_predict = predict_active(model=model, x=x)
    metrics = evaluation_metrics(y_true, y_predict)
    logger.info(
        "Evaluation metrics generated", dataset_name=dataset_name, metrics=metrics
    )
    return metrics


def _save_model(model, path: str):
    logger.info("Saving model", path=path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        joblib.dump(model, f)
    logger.info("Model saved successfully", path=path)


@click.command()
@click.option(
    "--train-features",
    "train_features_path",
    type=str,
    required=True,
    help="Path to the input features file.",
)
@click.option(
    "--train-labels",
    "train_labels_path",
    type=str,
    required=True,
    help="Path to the input label file.",
)
@click.option(
    "--validation-features",
    "validation_features_path",
    type=str,
    required=True,
    help="Path to the input features file.",
)
@click.option(
    "--validation-labels",
    "validation_labels_path",
    type=str,
    required=True,
    help="Path to the input label file.",
)
@click.option(
    "--model-path",
    "model_path",
    type=str,
    required=True,
    help="Output path to save the model.",
)
@click.option(
    "--features",
    "-f",
    multiple=True,
    type=click.Choice(list(FEATURE_COLS), case_sensitive=False),
    default=list(FEATURE_COLS),
    show_default=True,
    help="Features to use.",
)
@click.option(
    "--active-percentile",
    type=float,
    default=1.0,
    show_default=True,
    help="Active percentile.",
)
@wide_log(logger)
def train_model(
    train_features_path: str,
    train_labels_path: str,
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
    active_percentile: float,
):
    click.echo(f"Training surrogate model using features from {train_features_path}...")

    if _model_is_valid(model_path, active_percentile):
        logger.info(
            "Model already valid, skipping training",
            model_path=model_path,
            active_percentile=active_percentile,
        )
        click.echo("Done!")
        return

    logger.info(
        "Training surrogate model",
        train_features_path=train_features_path,
        train_labels_path=train_labels_path,
        validation_features_path=validation_features_path,
        validation_labels_path=validation_labels_path,
    )

    x_initial, y_initial_label, threshold = _prepare_dataset(
        train_features_path,
        train_labels_path,
        features,
        percentile=active_percentile,
    )

    x_initial_train, x_initial_test, y_initial_train, y_initial_test = train_test_split(
        x_initial, y_initial_label, train_size=0.8, random_state=RANDOM_SEED
    )

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=100,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=10,
        random_state=RANDOM_SEED,
        deterministic=True,
        force_row_wise=True,
    )

    time_start = time.perf_counter()
    model.fit(x_initial_train, y_initial_train)

    logger.info(
        "Trained model",
        samples=len(x_initial_train),
        duration_seconds=round(time.perf_counter() - time_start, 3),
    )

    _evaluate_and_log(
        model, x_initial_test, y_initial_test, dataset_name="Initial Split"
    )

    x_validation, y_validation_label, _ = _prepare_dataset(
        validation_features_path,
        validation_labels_path,
        features,
        threshold=threshold,
    )

    _evaluate_and_log(
        model, x_validation, y_validation_label, dataset_name="Validation"
    )

    _save_model(model, model_path)

    _write_success_marker(model_path, active_percentile)

    click.echo("Done!")
