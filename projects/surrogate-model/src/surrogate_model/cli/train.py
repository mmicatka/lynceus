# projects/surrogate-model/src/surrogate_model/cli/train.py

import os
import time

import click
import joblib
import lightgbm as lgb
import polars as pl
from lynceus_core.logging import get_lynceus_logger, wide_log
from sklearn.model_selection import train_test_split

from surrogate_model.common.cli import (
    features_option,
)
from surrogate_model.common.data import (
    compute_labels,
    flatten_features,
    load_and_clean_data,
)
from surrogate_model.common.io import manifest_valid, write_manifest
from surrogate_model.common.metrics import evaluation_metrics, predict_active

RANDOM_SEED = 1000

logger = get_lynceus_logger()


def _manifest_path(model_path: str) -> str:
    return f"{model_path}.manifest.json"


def _count_rows(path: str) -> int:
    return pl.scan_parquet(path).select(pl.len()).collect().item()


def _build_manifest(
    train_features_path: str,
    train_labels_path: str,
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    threshold: float,
) -> dict:
    return {
        "train_files": {
            "features": train_features_path,
            "labels": train_labels_path,
        },
        "validation_files": {
            "features": validation_features_path,
            "labels": validation_labels_path,
        },
        "features": list(features),
        "threshold": threshold,
        "num_samples": _count_rows(train_features_path),
        "num_validation_samples": _count_rows(validation_features_path),
        "seed": RANDOM_SEED,
    }


def _prepare_dataset(
    features_path: str, labels_path: str, features: list[str], threshold: float
) -> tuple:
    raw_features = pl.read_parquet(features_path)
    raw_labels = pl.read_parquet(labels_path)

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
    "--threshold",
    type=float,
    default=None,
    help="Affinity cutoff (kcal/mol) defining active. ",
)
@features_option
@wide_log(logger)
def train_model(
    train_features_path: str,
    train_labels_path: str,
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
    threshold: float,
):
    click.echo(f"Training surrogate model using features from {train_features_path}...")

    manifest = _build_manifest(
        train_features_path=train_features_path,
        train_labels_path=train_labels_path,
        validation_features_path=validation_features_path,
        validation_labels_path=validation_labels_path,
        features=features,
        threshold=threshold,
    )
    manifest_path = _manifest_path(model_path)

    if manifest_valid(manifest_path, manifest):
        logger.info(
            "Model already valid, skipping training",
            manifest_path=manifest_path,
        )
        click.echo("Done!")
        return

    logger.info(
        "Training surrogate model",
        train_features_path=train_features_path,
        train_labels_path=train_labels_path,
        validation_features_path=validation_features_path,
        validation_labels_path=validation_labels_path,
        num_samples=manifest["num_samples"],
    )

    x_initial, y_initial_label = _prepare_dataset(
        train_features_path,
        train_labels_path,
        features,
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

    write_manifest(
        manifest_path,
        {
            **manifest,
            "threshold": threshold,
            "num_train_samples": len(x_initial_train),
            "metrics": metrics_list,
        },
    )

    click.echo("Done!")
