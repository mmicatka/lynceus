# projects/surrogate-model/src/surrogate_model/cli/sample_by_prediction.py

from pathlib import Path

import click
import joblib
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger, wide_log

from surrogate_model.cli.sample import DEFAULT_BATCH_SIZE
from surrogate_model.common.cli import (
    features_option,
    label_definition_options,
    require_single_label_definition,
)
from surrogate_model.common.data import flatten_features
from surrogate_model.common.io import (
    count_rows,
    manifest_valid,
    resolve_parquet_files,
    stream_tables,
    verify_written,
    write_aligned_selection,
    write_manifest,
)
from surrogate_model.common.metrics import predict_active
from surrogate_model.common.model import ProbabilisticClassifier

VALID_SUFFIX = "_valid"
GROUP_COLUMN = "selection_group"
SCORE_COLUMN = "surrogate_score"
ACTIVE_GROUP = "active"
RANDOM_GROUP = "random"
DEFAULT_PROBABILITY_THRESHOLD = 0.5


logger = get_lynceus_logger()


def _load_model(model_path: str) -> ProbabilisticClassifier:
    return joblib.load(model_path)


def _valid_columns(file: str) -> list[str]:
    return [
        name
        for name in pq.ParquetFile(file).schema_arrow.names
        if name.endswith(VALID_SUFFIX)
    ]


def _to_dataframe(table: pa.Table) -> pl.DataFrame:
    return pl.DataFrame(table)


def _score_chunk(
    model: ProbabilisticClassifier,
    chunk: pa.Table,
    feature_cols: list[str],
    valid_cols: list[str],
) -> np.ndarray:
    df = _to_dataframe(chunk)
    scores = np.full(df.height, np.nan, dtype=np.float32)
    if valid_cols:
        eligible = (
            df.select(pl.all_horizontal(valid_cols).fill_null(False))
            .to_series()
            .to_numpy()
        )
    else:
        eligible = np.ones(df.height, dtype=bool)
    if eligible.any():
        x = flatten_features(df.filter(pl.Series(eligible)), feature_cols)
        scores[eligible] = predict_active(model, x)
    return scores


def _score_all(
    model: ProbabilisticClassifier,
    features_files: list[str],
    feature_cols: list[str],
    valid_cols: list[str],
    total_rows: int,
    batch_size: int,
) -> np.ndarray:
    scores = np.empty(total_rows, dtype=np.float32)
    columns = [*feature_cols, *valid_cols]
    offset = 0
    for chunk in stream_tables(features_files, columns, batch_size):
        end = offset + chunk.num_rows
        scores[offset:end] = _score_chunk(model, chunk, feature_cols, valid_cols)
        offset = end
    return scores


def _select_active(
    scores: np.ndarray,
    probability_threshold: float,
    num_active: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    with np.errstate(invalid="ignore"):
        active_positions = np.flatnonzero(scores >= probability_threshold)
    n_active_total = len(active_positions)
    k = min(num_active, n_active_total)
    if k == n_active_total:
        return active_positions, n_active_total
    return np.sort(rng.choice(active_positions, size=k, replace=False)), n_active_total


def _select_inactive(
    scores: np.ndarray,
    probability_threshold: float,
    num_random: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    with np.errstate(invalid="ignore"):
        inactive_positions = np.flatnonzero(scores < probability_threshold)
    k = min(num_random, len(inactive_positions))
    return np.sort(rng.choice(inactive_positions, size=k, replace=False)), len(
        inactive_positions
    )


def _combine(
    active: np.ndarray, random: np.ndarray, scores: np.ndarray
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    positions = np.concatenate([active, random])
    groups = np.array(
        [ACTIVE_GROUP] * len(active) + [RANDOM_GROUP] * len(random), dtype=object
    )
    order = np.argsort(positions, kind="stable")
    positions = positions[order]
    return positions, {
        SCORE_COLUMN: scores[positions],
        GROUP_COLUMN: groups[order],
    }


@click.command("sample_by_prediction")
@click.option("--features-input", "features_input", required=True, type=str)
@click.option("--conformers-input", "conformers_input", required=True, type=str)
@click.option(
    "--model",
    "model_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Saved LightGBM model (.joblib).",
)
@features_option
@label_definition_options
@click.option("--output", "output_path", required=True, type=click.Path(dir_okay=False))
@click.option(
    "--num-active",
    "num_active",
    required=True,
    type=click.IntRange(min=0),
    help="Number of predicted-active rows to keep.",
)
@click.option(
    "--num-random",
    "num_random",
    required=True,
    type=click.IntRange(min=0),
    help="Number of uniformly sampled predicted-inactive rows to add.",
)
@click.option(
    "--probability-threshold",
    "probability_threshold",
    default=DEFAULT_PROBABILITY_THRESHOLD,
    show_default=True,
    type=click.FloatRange(0.0, 1.0),
    help="Rows with P(active) >= this value are labelled active.",
)
@click.option("--id-column", "id_column", default="id", show_default=True, type=str)
@click.option(
    "--batch-size",
    "batch_size",
    default=DEFAULT_BATCH_SIZE,
    show_default=True,
    type=click.IntRange(min=1),
)
@click.option("--seed", "seed", default=None, type=int)
@wide_log(logger)
def sample_by_prediction(
    features_input: str,
    conformers_input: str,
    model_path: str,
    features: tuple[str, ...],
    active_percentile: float | None,
    threshold: float | None,
    output_path: str,
    num_active: int,
    num_random: int,
    probability_threshold: float,
    id_column: str,
    batch_size: int,
    seed: int | None,
) -> None:
    require_single_label_definition(active_percentile, threshold)

    click.echo(
        f"Sampling by prediction from {features_input} and {conformers_input}..."
    )

    identifier = Path(output_path).stem
    feature_cols = list(features)

    features_files = resolve_parquet_files(features_input)
    conformers_files = resolve_parquet_files(conformers_input)

    manifest = {
        "features_files": features_files,
        "conformers_files": conformers_files,
        "num_active": num_active,
        "num_random": num_random,
        "feature_cols": feature_cols,
        "seed": seed,
    }

    manifest_path = f"{output_path}.manifest.json"

    if manifest_valid(manifest_path, manifest):
        logger.info(
            "Sample already valid, skipping generation",
            manifest_path=manifest_path,
        )
        click.echo("Done!")
        return

    features_files = resolve_parquet_files(features_input)
    conformers_files = resolve_parquet_files(conformers_input)

    total_rows = count_rows(features_files)
    conformer_rows = count_rows(conformers_files)
    if total_rows != conformer_rows:
        raise RuntimeError(
            f"Row count mismatch: {total_rows} features vs {conformer_rows} conformers"
        )

    model = _load_model(model_path)
    valid_cols = _valid_columns(features_files[0])

    logger.info(
        "Scoring library with surrogate model",
        identifier=identifier,
        model_path=model_path,
        total_rows=total_rows,
        features=feature_cols,
        training_active_percentile=active_percentile,
        training_threshold=threshold,
    )
    scores = _score_all(
        model, features_files, feature_cols, valid_cols, total_rows, batch_size
    )

    rng = np.random.default_rng(seed)
    active, n_active_total = _select_active(
        scores, probability_threshold, num_active, rng
    )
    random, n_inactive_total = _select_inactive(
        scores, probability_threshold, num_random, rng
    )

    if len(active) < num_active:
        logger.warning(
            "Fewer active rows than requested, keeping all",
            identifier=identifier,
            requested=num_active,
            available=n_active_total,
        )
    if len(random) < num_random:
        logger.warning(
            "Fewer inactive rows than requested, keeping all",
            identifier=identifier,
            requested=num_random,
            available=n_inactive_total,
        )

    positions, extra_columns = _combine(active, random, scores)

    logger.info(
        "Writing prediction-based sample",
        identifier=identifier,
        num_active=len(active),
        num_random=len(random),
        active_total=n_active_total,
        inactive_total=n_inactive_total,
        probability_threshold=probability_threshold,
        output_path=output_path,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    write_aligned_selection(
        features_files=features_files,
        conformers_files=conformers_files,
        positions=positions,
        output_file=output_path,
        id_column=id_column,
        batch_size=batch_size,
        extra_columns=extra_columns,
    )
    verify_written(output_path, len(positions))
    write_manifest(manifest_path, manifest)

    logger.info(
        "Finished prediction-based sampling",
        identifier=identifier,
        num_samples=len(positions),
        output_path=output_path,
    )
    click.echo("Done!")
