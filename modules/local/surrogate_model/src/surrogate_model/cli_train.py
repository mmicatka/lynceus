# modules/local/surrogate_model/src/surrogate_model/train.py

import logging
import sys

import click
import fsspec
import lightgbm as lgb
import polars as pl
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
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


def qualify_path(path: str, bucket: str) -> str:
    return f"s3://{bucket}/{path}" if bucket else path


def read_parquet(path: str, fs: fsspec.AbstractFileSystem) -> pl.DataFrame:
    return pl.read_parquet(fs.cat_file(path))


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
    "--validate-features",
    "validate_features_path",
    type=str,
    required=True,
    help="Path to the input features file.",
)
@click.option(
    "--validate-labels",
    "validate_labels_path",
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
    help="Features to generate.",
)
def train_model(
    train_features_path: str,
    train_labels_path: str,
    validate_features_path: str,
    validate_labels_path: str,
    features: list[str],
    model_path: str,
    bucket: str,
):
    logger.info(
        "training surrogate model using features: %s\tlabels: %s",
        train_features_path,
        train_labels_path,
    )

    logger.info(
        "validating using features: %s\tlabels: %s",
        validate_features_path,
        validate_labels_path,
    )

    blob_storage_settings = get_blob_storage_settings() if bucket else None
    fs = get_filesystem(blob_storage_settings)

    train_features_path = (
        f"s3://{bucket}/{train_features_path}" if bucket else train_features_path
    )
    train_labels_path = (
        f"s3://{bucket}/{train_labels_path}" if bucket else train_labels_path
    )

    train_features = read_parquet(train_features_path, fs)
    train_labels = read_parquet(train_labels_path, fs)

    df_train = load_and_clean_data(train_features, train_labels)

    x_initial = flatten_features(df_train, features)
    y_initial_raw = df_train["affinity_kcal_mol"]

    # "top" 1% (most negative == strongest binder)
    y_initial_label, threshold = label(y_initial_raw, percentile=1.0)

    x_initial_train, x_initial_test, y_initial_train, y_initial_test = train_test_split(
        x_initial, y_initial_label, train_size=0.8, random_state=RANDOM_SEED
    )

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=10,
        random_state=RANDOM_SEED,
        deterministic=True,
        force_row_wise=True,
    )

    model.fit(x_initial_train, y_initial_train)

    y_predict_initial = predict_active(model=model, x=x_initial_test)
    df_metrics_initial = evaluation_metrics(y_initial_test, y_predict_initial)

    print(df_metrics_initial)
