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
from lynceus_core.logging import wide_log
from sklearn.model_selection import train_test_split

from surrogate_model.common.cli import (
    features_option,
    label_definition_options,
    require_single_label_definition,
)
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
    base_path = output_path.removesuffix(".joblib")
    return f"{base_path}.results.json"


def _model_is_valid(
    output_path: str, active_percentile: Optional[float], threshold: Optional[float]
) -> bool:
    marker_path = _marker_path(output_path)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        data = json.load(f)
        # Validate against whichever parameter the user provided
        if active_percentile is not None:
            return data.get("active_percentile") == active_percentile
        if threshold is not None:
            return data.get("threshold") == threshold
        return False


def _write_success_marker(
    output_path: str,
    active_percentile: Optional[float],
    threshold: Optional[float],
    train_features: str,
    train_labels: str,
    validation_features: str,
    validation_labels: str,
    metrics: list[dict],
) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(_marker_path(output_path), "w") as f:
        json.dump(
            {
                "active_percentile": active_percentile,
                "threshold": threshold,
                "train_files": {
                    "features": train_features,
                    "labels": train_labels,
                },
                "validation_files": {
                    "features": validation_features,
                    "labels": validation_labels,
                },
                "metrics": metrics,
            },
            f,
            indent=2,
        )


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

    # "top" % (most negative == strongest binder) or use provided threshold
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
@features_option
@label_definition_options
@wide_log(logger)
def train_model(
    train_features_path: str,
    train_labels_path: str,
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
    active_percentile: float | None,
    threshold: float | None,
):
    require_single_label_definition(active_percentile, threshold)

    click.echo(f"Training surrogate model using features from {train_features_path}...")

    if _model_is_valid(
        model_path, active_percentile=active_percentile, threshold=threshold
    ):
        logger.info(
            "Model already valid, skipping training",
            model_path=model_path,
            active_percentile=active_percentile,
            threshold=threshold,
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

    x_initial, y_initial_label, dataset_threshold = _prepare_dataset(
        train_features_path,
        train_labels_path,
        features,
        percentile=active_percentile,
        threshold=threshold,
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
        threshold=dataset_threshold,
    )

    val_metrics_df = _evaluate_and_log(
        model, x_validation, y_validation_label, dataset_name="Validation"
    )

    metrics_list = (
        val_metrics_df.to_dicts()
        if isinstance(val_metrics_df, pl.DataFrame)
        else val_metrics_df
    )

    _save_model(model, model_path)

    _write_success_marker(
        output_path=model_path,
        active_percentile=active_percentile,
        threshold=threshold,
        train_features=train_features_path,
        train_labels=train_labels_path,
        validation_features=validation_features_path,
        validation_labels=validation_labels_path,
        metrics=metrics_list,
    )

    click.echo("Done!")
