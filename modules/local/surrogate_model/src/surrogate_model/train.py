# modules/local/surrogate_model/src/surrogate_model/train.py

# modules/local/surrogate_sampling/train_surrogate.py

import json
import os
import tempfile

import click
import duckdb
import joblib
from lightgbm import LGBMClassifier
from lynceus_utils import get_blob_storage_settings, get_connection, get_filesystem
from lynceus_utils.storage import BlobStorageSettings

ROUND_PATTERN = r"round_(\d+)/"


def _blob_path(use_blob_storage: bool, bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}" if use_blob_storage else key


def _output_is_valid(
    filesystem,
    output_path: str,
    train_path: str,
    test_path: str,
    max_round_index: int,
    num_leaves: int,
    n_estimators: int,
    learning_rate: float,
) -> bool:
    manifest_path = f"{output_path}.manifest.json"
    if not filesystem.exists(manifest_path) or not filesystem.exists(output_path):
        return False

    with filesystem.open(manifest_path, "r") as f:
        manifest = json.load(f)

    return (
        manifest.get("train_path") == train_path
        and manifest.get("test_path") == test_path
        and manifest.get("max_round_index") == max_round_index
        and manifest.get("num_leaves") == num_leaves
        and manifest.get("n_estimators") == n_estimators
        and manifest.get("learning_rate") == learning_rate
    )


def _write_manifest(
    filesystem,
    output_path: str,
    train_path: str,
    test_path: str,
    max_round_index: int,
    num_leaves: int,
    n_estimators: int,
    learning_rate: float,
) -> None:
    manifest = {
        "train_path": train_path,
        "test_path": test_path,
        "max_round_index": max_round_index,
        "num_leaves": num_leaves,
        "n_estimators": n_estimators,
        "learning_rate": learning_rate,
    }
    with filesystem.open(f"{output_path}.manifest.json", "w") as f:
        json.dump(manifest, f)


def _load_training_frame(
    con: duckdb.DuckDBPyConnection,
    labels_glob: str,
    features_glob: str,
    id_column: str,
    max_round_index: int,
):
    return con.sql(
        f"""
        WITH labels AS (
            SELECT
                {id_column},
                label,
                CAST(regexp_extract(filename, '{ROUND_PATTERN}', 1) AS INTEGER) AS round_index
            FROM read_parquet('{labels_glob}', filename = true)
        )
        SELECT f.*, l.label
        FROM labels AS l
        INNER JOIN read_parquet('{features_glob}') AS f
            ON f.{id_column} = l.{id_column}
        WHERE l.round_index <= {max_round_index}
        """
    ).df()


def _load_holdout_frame(
    con: duckdb.DuckDBPyConnection,
    holdout_labels_path: str,
    features_glob: str,
    id_column: str,
):
    return con.sql(
        f"""
        SELECT f.*, h.label
        FROM read_parquet('{holdout_labels_path}') AS h
        INNER JOIN read_parquet('{features_glob}') AS f
            ON f.{id_column} = h.{id_column}
        """
    ).df()


def _fit_model(
    frame,
    feature_columns: list[str],
    num_leaves: int,
    n_estimators: int,
    learning_rate: float,
    seed: int,
) -> LGBMClassifier:
    model = LGBMClassifier(
        num_leaves=num_leaves,
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        random_state=seed,
        deterministic=True,
        force_row_wise=True,
    )
    model.fit(frame[feature_columns], frame["label"])
    return model


def _evaluate(
    model: LGBMClassifier,
    holdout_frame,
    feature_columns: list[str],
    bedroc_alpha: float,
    ef_fraction: float,
) -> tuple[float, float]:
    scores = model.predict_proba(holdout_frame[feature_columns])[:, 1]
    labels = holdout_frame["label"].to_numpy()
    return (
        _bedroc_score(labels, scores, bedroc_alpha),
        _ef_at_fraction(labels, scores, ef_fraction),
    )


def _write_model(filesystem, output_path: str, model: LGBMClassifier) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, "model.joblib")
        joblib.dump(model, tmp_path)

        with filesystem.open(output_path, "wb") as dst, open(tmp_path, "rb") as src:
            dst.write(src.read())


@click.command()
@click.option("--train", "train_path", required=True)
@click.option("--test", "test_path", required=True)
@click.option("--output", "output_path", required=True)
@click.option("--max-round-index", type=int, required=True)
@click.option("--id-column", default="id", show_default=True)
@click.option("--num-leaves", type=int, default=31, show_default=True)
@click.option("--n-estimators", type=int, default=100, show_default=True)
@click.option("--learning-rate", type=float, default=0.1, show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--use-blob-storage", is_flag=True, default=False)
@click.option("--bucket", default="lynceus", show_default=True)
def train(
    train_path: str,
    test_path: str,
    output_path: str,
    max_round_index: int,
    id_column: str,
    num_leaves: int,
    n_estimators: int,
    learning_rate: float,
    seed: int,
    use_blob_storage: bool,
    bucket: str,
):
    blob_storage_settings: BlobStorageSettings | None = (
        get_blob_storage_settings() if use_blob_storage else None
    )
    filesystem = get_filesystem(blob_storage_settings)
    con = get_connection(blob_storage_settings)

    train_path = _blob_path(use_blob_storage, bucket, train_path)
    test_path = _blob_path(use_blob_storage, bucket, test_path)
    output_path = _blob_path(use_blob_storage, bucket, output_path)

    if _output_is_valid(
        filesystem,
        output_path,
        train_path,
        test_path,
        max_round_index,
        num_leaves,
        n_estimators,
        learning_rate,
    ):
        click.echo(f"train_surrogate: valid output already at {output_path}, skipping")
        return

    training_frame = _load_training_frame(
        con, resolved_labels_glob, resolved_features_glob, id_column, max_round_index
    )
    if training_frame.empty:
        raise RuntimeError(
            f"train_surrogate: no labeled rows found for {resolved_labels_glob} "
            f"up to round {max_round_index}"
        )

    holdout_frame = _load_holdout_frame(
        con, resolved_holdout_path, resolved_features_glob, id_column
    )
    if holdout_frame.empty:
        raise RuntimeError(
            f"train_surrogate: holdout set at {resolved_holdout_path} joined to "
            f"zero feature rows"
        )

    feature_columns = [
        c for c in training_frame.columns if c not in (id_column, "label")
    ]

    model = _fit_model(
        training_frame, feature_columns, num_leaves, n_estimators, learning_rate, seed
    )
    bedroc, ef_at_1pct = _evaluate(
        model, holdout_frame, feature_columns, bedroc_alpha, ef_fraction=0.01
    )

    _write_model(filesystem, output_path, model)
    _write_manifest(
        filesystem,
        output_path,
        resolved_labels_glob,
        resolved_features_glob,
        max_round_index,
        num_leaves,
        n_estimators,
        learning_rate,
        train_rows=len(training_frame),
        bedroc=bedroc,
        ef_at_1pct=ef_at_1pct,
    )

    click.echo(
        f"train_surrogate: trained on {len(training_frame)} rows "
        f"(rounds <= {max_round_index}), bedroc={bedroc:.4f}, "
        f"ef@1%={ef_at_1pct:.2f}, wrote {output_path}"
    )
