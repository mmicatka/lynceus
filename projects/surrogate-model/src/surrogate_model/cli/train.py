# projects/surrogate-model/src/surrogate_model/cli/train.py


import datetime
import time
from pathlib import Path

import click
import joblib
import lightgbm as lgb
import numpy as np
import polars as pl
from lynceus_core.cli import PATH_SEPARATOR, split_paths
from lynceus_core.io.staged_io import staged_output
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

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"

MANIFEST_FILE_SUFFIX = ".manifest.json"

logger = get_lynceus_logger()


def _input_manifest(
    input_files: list[str],
    model_path: str,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    manifest_path = Path(model_path).with_suffix(MANIFEST_FILE_SUFFIX)
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        input_files, source_root
    )


def _already_trained(manifest: Manifest, model_path: str) -> bool:
    return Path(model_path).is_file() and manifest.exists_superset()


def _expected_state(features: list[str], threshold: float) -> dict:
    return {
        "features": list(features),
        "threshold": threshold,
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


def _metrics_records(metrics: pl.DataFrame | list[dict]) -> list[dict]:
    return metrics.to_dicts() if isinstance(metrics, pl.DataFrame) else metrics


def _train_and_evaluate(
    train_features_paths: list[str],
    train_labels_paths: list[str],
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    threshold: float,
) -> tuple[lgb.LGBMClassifier, dict]:
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

    fit_start_time = time.perf_counter()
    model.fit(x_initial_train, y_initial_train)

    logger.info(
        "Trained model",
        samples=len(x_initial_train),
        duration_seconds=round(time.perf_counter() - fit_start_time, 3),
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

    validation_metrics = _evaluate_and_log(
        model, x_validation, y_validation_label, dataset_name="Validation"
    )

    results = {
        "num_train_samples": len(x_initial_train),
        "metrics": _metrics_records(validation_metrics),
    }
    return model, results


def _save_model(model, path: Path) -> None:
    logger.info("Saving model", path=str(path))
    with open(path, "wb") as f:
        joblib.dump(model, f)
    logger.info("Model saved successfully", path=str(path))


def _save_via_staged_output(model, model_path: Path, scratch_dir: str | None) -> None:
    with staged_output(
        model_path.parent,
        transfers=STAGED_OUTPUT_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        _save_model(model, local_output / model_path.name)


@click.command()
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
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
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the model file before it is copied to --model-path "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def train_model(
    source_root: Path,
    train_features_paths: list[str],
    train_labels_paths: list[str],
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
    scratch_dir: str | None,
) -> None:
    click.echo(
        f"Training surrogate model using {len(train_features_paths)} feature files..."
    )

    threshold = get_validation_threshold(validation_labels_path)

    logger.info("threshold", threshold=threshold)

    manifest = _input_manifest(
        [
            *train_features_paths,
            *train_labels_paths,
            validation_features_path,
            validation_labels_path,
        ],
        model_path,
        source_root,
        _expected_state(features, threshold),
    )

    try:
        if _already_trained(manifest, model_path):
            logger.info("Valid manifest found.", manifest=manifest.data)
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Training surrogate model",
        manifest=manifest.data,
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    model, results = _train_and_evaluate(
        train_features_paths,
        train_labels_paths,
        validation_features_path,
        validation_labels_path,
        features,
        threshold,
    )

    _save_via_staged_output(model, Path(model_path), scratch_dir)

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.data.update(results)
    manifest.save()

    click.echo("Done!")
