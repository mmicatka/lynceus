# projects/surrogate-model/src/surrogate_model/cli/sample_by_prediction.py


from pathlib import Path

import click
import joblib
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger, wide_log

from surrogate_model.common.cli import features_option
from surrogate_model.common.data import flatten_features
from surrogate_model.common.io import (
    DEFAULT_BATCH_SIZE,
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

DEFAULT_RANDOM_SEED = 1000

VALID_SUFFIX = "_valid"
GROUP_COLUMN = "selection_group"
TOP_GROUP = "top"
RANDOM_GROUP = "random"


logger = get_lynceus_logger()


def _load_model(model_path: str) -> ProbabilisticClassifier:
    return joblib.load(model_path)


def _valid_columns(file: str) -> list[str]:
    return [
        name
        for name in pq.ParquetFile(file).schema_arrow.names
        if name.endswith(VALID_SUFFIX)
    ]


def _score_chunk(
    model: ProbabilisticClassifier,
    chunk: pa.Table,
    feature_cols: list[str],
    valid_cols: list[str],
) -> np.ndarray:
    df = pl.DataFrame(chunk)
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


def _select_top(scores: np.ndarray, num_top: int) -> tuple[np.ndarray, int]:
    scored_positions = np.flatnonzero(~np.isnan(scores))
    n_scored = len(scored_positions)
    k = min(num_top, n_scored)
    if k == 0:
        return np.empty(0, dtype=np.int64), n_scored
    if k == n_scored:
        return scored_positions, n_scored
    top = np.argpartition(scores[scored_positions], -k)[-k:]
    return np.sort(scored_positions[top]), n_scored


def _select_random(
    scores: np.ndarray,
    excluded: np.ndarray,
    num_random: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    candidates = ~np.isnan(scores)
    candidates[excluded] = False
    remaining_positions = np.flatnonzero(candidates)
    k = min(num_random, len(remaining_positions))
    chosen = rng.choice(remaining_positions, size=k, replace=False)
    return np.sort(chosen), len(remaining_positions)


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
@click.option("--output", "output_path", required=True, type=click.Path(dir_okay=False))
@click.option(
    "--num-top",
    "num_top",
    required=True,
    type=click.IntRange(min=0),
    help="Number of highest-scoring rows to keep.",
)
@click.option(
    "--num-random",
    "num_random",
    required=True,
    type=click.IntRange(min=0),
    help="Number of randomly sampled rows to add from the remaining rows.",
)
@click.option("--id-column", "id_column", default="id", show_default=True, type=str)
@click.option(
    "--batch-size",
    "batch_size",
    default=DEFAULT_BATCH_SIZE,
    show_default=True,
    type=click.IntRange(min=1),
)
@click.option("--seed", "seed", default=DEFAULT_RANDOM_SEED, type=int)
@wide_log(logger)
def sample_candidates_by_prediction(
    features_input: str,
    conformers_input: str,
    model_path: str,
    features: tuple[str, ...],
    output_path: str,
    num_top: int,
    num_random: int,
    id_column: str,
    batch_size: int,
    seed: int,
) -> None:
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
        "num_top": num_top,
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
    )
    scores = _score_all(
        model, features_files, feature_cols, valid_cols, total_rows, batch_size
    )

    rng = np.random.default_rng(seed)
    top, n_scored = _select_top(scores, num_top)
    random, n_remaining = _select_random(scores, top, num_random, rng)

    if len(top) < num_top:
        logger.warning(
            "Fewer scored rows than requested top, keeping all",
            identifier=identifier,
            requested=num_top,
            available=n_scored,
        )
    if len(random) < num_random:
        logger.warning(
            "Fewer remaining rows than requested random, keeping all",
            identifier=identifier,
            requested=num_random,
            available=n_remaining,
        )

    positions = np.concatenate([top, random])

    logger.info(
        "Writing prediction-based sample",
        identifier=identifier,
        num_top=len(top),
        num_random=len(random),
        scored_total=n_scored,
        remaining_total=n_remaining,
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
