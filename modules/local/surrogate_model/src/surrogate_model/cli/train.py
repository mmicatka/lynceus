# modules/local/surrogate_model/src/surrogate_model/train.py

import logging
import sys
import time

import click
import fsspec
import joblib
import lightgbm as lgb
import polars as pl
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem, resolve_path
from sklearn.model_selection import train_test_split

from surrogate_model.data import flatten_features, label, load_and_clean_data
from surrogate_model.metrics import evaluation_metrics, predict_active

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

RANDOM_SEED = 1000
FEATURE_COLS = [
    "atom_pair",
    "autocorr",
    "descriptors",
    "ecfp",
    "functional_groups",
    "morse",
    "rdf",
    "topological_torsion",
    "usrcat",
    "whim",
]


def _read_parquet(path: str, fs: fsspec.AbstractFileSystem) -> pl.DataFrame:
    return pl.read_parquet(fs.cat_file(path))


def _prepare_dataset(
    features_path: str,
    labels_path: str,
    fs: fsspec.AbstractFileSystem,
    features: list[str],
    percentile: float = None,
    threshold: float = None,
) -> tuple:
    raw_features = _read_parquet(features_path, fs)
    raw_labels = _read_parquet(labels_path, fs)

    df_cleaned = load_and_clean_data(raw_features, raw_labels)

    x = flatten_features(df_cleaned, features)
    y_raw = df_cleaned["affinity_kcal_mol"]

    # "top" 1% (most negative == strongest binder) or use provided threshold
    y_label, computed_threshold = label(
        y_raw, percentile=percentile, threshold=threshold
    )

    return x, y_label, computed_threshold


def _evaluate_and_log(model, x, y_true, dataset_name: str) -> pl.DataFrame:
    y_predict = predict_active(model=model, x=x)
    metrics = evaluation_metrics(y_true, y_predict)
    logger.info(f"{dataset_name} Evaluation Metrics:\n{metrics}")
    return metrics


def _save_model(model, path: str, fs: fsspec.AbstractFileSystem):
    logger.info("Saving model to %s...", path)
    with fs.open(path, "wb") as f:
        joblib.dump(model, f)
    logger.info("Model saved successfully.")


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
@click.option("--bucket", type=str, default="", help="S3-compatible bucket name.")
@click.option(
    "--features",
    "-f",
    multiple=True,
    type=click.Choice(list(FEATURE_COLS), case_sensitive=False),
    default=list(FEATURE_COLS),
    show_default=True,
    help="Features to use.",
)
@click.option("--active-percentile", type=float, default=1.0, help="Active percentile.")
def train_model(
    train_features_path: str,
    train_labels_path: str,
    validation_features_path: str,
    validation_labels_path: str,
    features: list[str],
    model_path: str,
    bucket: str,
    active_percentile: float,
):
    train_features_path = resolve_path(train_features_path, bucket)
    train_labels_path = resolve_path(train_labels_path, bucket)
    validation_features_path = resolve_path(validation_features_path, bucket)
    validation_labels_path = resolve_path(validation_labels_path, bucket)

    logger.info(
        "training surrogate model using features: %s\tlabels: %s",
        train_features_path,
        train_labels_path,
    )

    logger.info(
        "validating using features: %s\tlabels: %s",
        validation_features_path,
        validation_labels_path,
    )

    blob_storage_settings = get_blob_storage_settings() if bucket else None
    fs = get_filesystem(blob_storage_settings)

    x_initial, y_initial_label, threshold = _prepare_dataset(
        train_features_path,
        train_labels_path,
        fs,
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
        "trained model with: %d samples in %.3fs",
        len(x_initial_train),
        time.perf_counter() - time_start,
    )

    _evaluate_and_log(
        model, x_initial_test, y_initial_test, dataset_name="Initial Split"
    )

    x_validation, y_validation_label, _ = _prepare_dataset(
        validation_features_path,
        validation_labels_path,
        fs,
        features,
        threshold=threshold,
    )

    _evaluate_and_log(
        model, x_validation, y_validation_label, dataset_name="Validation"
    )

    _save_model(model, model_path, fs)
