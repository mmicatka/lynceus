# projects/surrogate-model/src/surrogate_model/cli/train.py

import datetime
import os
import time
from pathlib import Path

import click
import joblib
import lightgbm as lgb
import numpy as np
import polars as pl
from lynceus_core.cli import PATH_SEPARATOR, split_paths
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest
from sklearn.model_selection import train_test_split

from surrogate_model.common.cli import (
    features_option,
)
from surrogate_model.common.data import (
    compute_labels,
    flatten_features,
    load_and_clean_data,
)
from surrogate_model.common.metrics import evaluation_metrics, predict_active
from surrogate_model.common.threshold import get_validation_threshold

RANDOM_SEED = 1000

logger = get_lynceus_logger()


def _count_rows(paths: list[str]) -> int:
    return pl.scan_parquet(paths).select(pl.len()).collect().item()


def _build_manifest(
    train_features_paths: list[str],
    train_labels_paths: list[str],
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    threshold: float,
) -> dict:
    return {
        "train_files": {
            "features": train_features_paths,
            "labels": train_labels_paths,
        },
        "validation_files": {
            "features": validation_features_path,
            "labels": validation_labels_path,
        },
        "features": list(features),
        "threshold": threshold,
        "num_samples": _count_rows(train_features_paths),
        "num_validation_samples": _count_rows([validation_features_path]),
        "seed": RANDOM_SEED,
    }


def _prepare_dataset(
    features_paths: list[str],
    labels_paths: list[str],
    features: list[str],
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    raw_features = pl.read_parquet(features_paths)
    raw_labels = pl.read_parquet(labels_paths)

    df_cleaned = load_and_clean_data(raw_features, raw_labels)

    x = flatten_features(df_cleaned, features)
    y_raw = df_cleaned["affinity_kcal_mol"]

    y_label = compute_labels(y_raw, threshold=threshold)

    return x, y_label


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
    "train_features_paths",
    type=str,
    required=True,
    callback=split_paths,
    help=f"{PATH_SEPARATOR}-separated paths to the input features files.",
)
@click.option(
    "--train-labels",
    "train_labels_paths",
    type=str,
    required=True,
    callback=split_paths,
    help=f"{PATH_SEPARATOR}-separated paths to the input label files.",
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
@wide_log(logger)
def train_model(
    train_features_paths: list[str],
    train_labels_paths: list[str],
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
):
    click.echo(
        f"Training surrogate model using {len(train_features_paths)} feature files..."
    )

    threshold = get_validation_threshold(validation_labels_path)

    logger.info("threshold", threshold=threshold)

    manifest_data = _build_manifest(
        train_features_paths=train_features_paths,
        train_labels_paths=train_labels_paths,
        validation_features_path=validation_features_path,
        validation_labels_path=validation_labels_path,
        features=features,
        threshold=threshold,
    )

    manifest_path = str(Path(model_path).with_suffix(".manifest.json"))

    manifest = Manifest(data=manifest_data, filepath=manifest_path)

    try:
        if manifest.exists_superset():
            logger.info(
                "Valid manifest found.",
                manifest=manifest.data,
            )
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))
    logger.info(
        "Training surrogate model",
        manifest=manifest_data,
    )

    x_initial, y_initial_label = _prepare_dataset(
        train_features_paths,
        train_labels_paths,
        features,
        threshold=threshold,
    )

    logger.info("dataset", label_bins=np.bincount(y_initial_label))

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

    start_time = time.perf_counter()
    model.fit(x_initial_train, y_initial_train)

    logger.info(
        "Trained model",
        samples=len(x_initial_train),
        duration_seconds=round(time.perf_counter() - start_time, 3),
    )

    _evaluate_and_log(
        model, x_initial_test, y_initial_test, dataset_name="Initial Split"
    )

    x_validation, y_validation_label = _prepare_dataset(
        [validation_features_path],
        [validation_labels_path],
        features,
        threshold=threshold,
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

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.data = {
        **manifest.data,
        "num_train_samples": len(x_initial_train),
        "metrics": metrics_list,
    }

    manifest.save()

    click.echo("Done!")
