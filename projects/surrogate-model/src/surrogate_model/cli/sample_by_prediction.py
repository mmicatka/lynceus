# projects/surrogate-model/src/surrogate_model/cli/sample_by_prediction.py


import datetime
import time
from pathlib import Path

import click
import joblib
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

from surrogate_model.common.cli import featurized_option
from surrogate_model.common.data import flatten_featurized
from surrogate_model.common.io import (
    DEFAULT_BATCH_SIZE,
    count_rows,
    resolve_parquet_files,
    stream_tables,
    verify_written,
    write_aligned_selection,
)
from surrogate_model.common.metrics import predict_active
from surrogate_model.common.model import ProbabilisticClassifier

DEFAULT_RANDOM_SEED = 1000

VALID_SUFFIX = "_valid"
GROUP_COLUMN = "selection_group"
TOP_GROUP = "top"
RANDOM_GROUP = "random"

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"
PATH_SEPARATOR = ","
MANIFEST_FILE_SUFFIX = ".manifest.json"


logger = get_lynceus_logger()


def _input_manifest(
    input_files: list[str],
    output_path: str,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    manifest_path = Path(output_path).with_suffix(MANIFEST_FILE_SUFFIX)
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        input_files, source_root
    )


def _already_sampled(manifest: Manifest, output_path: str) -> bool:
    return Path(output_path).is_file() and manifest.exists_superset()


def _load_model(model_path: str) -> ProbabilisticClassifier:
    return joblib.load(model_path)


def _valid_columns(file: str) -> list[str]:
    return [
        name
        for name in pq.ParquetFile(file).schema_arrow.names
        if name.endswith(VALID_SUFFIX)
    ]


def _split_paths(value: str | None) -> list[str]:
    if value is None:
        return []
    return [
        path for path in (part.strip() for part in value.split(PATH_SEPARATOR)) if path
    ]


def _exclusion_files(exclude_inputs: tuple[str, ...], output_path: str) -> list[str]:
    output = Path(output_path)
    return [
        file
        for pattern in exclude_inputs
        for file in resolve_parquet_files(pattern)
        if Path(file) != output
    ]


def _load_excluded_ids(
    files: list[str], id_column: str, id_type: pa.DataType
) -> pa.Array | None:
    if not files:
        return None
    ids = (
        pa.concat_tables([pq.read_table(file, columns=[id_column]) for file in files])
        .column(id_column)
        .combine_chunks()
    )
    if ids.type != id_type:
        raise RuntimeError(
            f"Excluded id type {ids.type} does not match featurized id type {id_type}"
        )
    return ids


def _eligible_mask(
    chunk: pa.Table,
    valid_cols: list[str],
    id_column: str,
    excluded_ids: pa.Array | None,
) -> np.ndarray:
    mask = np.ones(chunk.num_rows, dtype=bool)
    if valid_cols:
        mask &= (
            pl.DataFrame(chunk.select(valid_cols))
            .select(pl.all_horizontal(valid_cols).fill_null(False))
            .to_series()
            .to_numpy()
        )
    if excluded_ids is not None:
        mask &= ~chunk.column(id_column).isin(excluded_ids).to_numpy()
    return mask


def _score_chunk(
    model: ProbabilisticClassifier,
    chunk: pa.Table,
    feature_cols: list[str],
    valid_cols: list[str],
    id_column: str,
    excluded_ids: pa.Array | None,
) -> np.ndarray:
    scores = np.full(chunk.num_rows, np.nan, dtype=np.float32)
    eligible = _eligible_mask(chunk, valid_cols, id_column, excluded_ids)
    if eligible.any():
        x = flatten_featurized(
            pl.DataFrame(chunk).filter(pl.Series(eligible)), feature_cols
        )
        scores[eligible] = predict_active(model, x)
    return scores


def _score_all(
    model: ProbabilisticClassifier,
    featurized_files: list[str],
    feature_cols: list[str],
    valid_cols: list[str],
    id_column: str,
    excluded_ids: pa.Array | None,
    total_rows: int,
    batch_size: int,
) -> np.ndarray:
    scores = np.empty(total_rows, dtype=np.float32)
    columns = [id_column, *feature_cols, *valid_cols]
    offset = 0
    for chunk in stream_tables(featurized_files, columns, batch_size):
        end = offset + chunk.num_rows
        scores[offset:end] = _score_chunk(
            model, chunk, feature_cols, valid_cols, id_column, excluded_ids
        )
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


def _write_selection_via_staged_output(
    featurized_files: list[str],
    preprocessed_files: list[str],
    positions: np.ndarray,
    output_path: Path,
    id_column: str,
    batch_size: int,
    scratch_dir: str | None,
) -> None:
    with staged_output(
        output_path.parent,
        transfers=STAGED_OUTPUT_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        local_file = local_output / output_path.name
        write_aligned_selection(
            featurized_files=featurized_files,
            preprocessed_files=preprocessed_files,
            positions=positions,
            output_file=str(local_file),
            id_column=id_column,
            batch_size=batch_size,
        )
        verify_written(str(local_file), len(positions))


@click.command("sample_by_prediction")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option("--featurized-input", "featurized_input", required=True, type=str)
@click.option("--preprocessed-input", "preprocessed_input", required=True, type=str)
@click.option(
    "--model",
    "model_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Saved LightGBM model (.joblib).",
)
@featurized_option
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
@click.option(
    "--exclude-input",
    "exclude_inputs",
    multiple=True,
    type=str,
    help="Parquet file(s) or glob of previously sampled rows to exclude by id."
    "Repeatable.",
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
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the sampled file before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def sample_candidates_by_prediction(
    source_root: Path,
    featurized_input: str,
    preprocessed_input: str,
    model_path: str,
    featurized: tuple[str, ...],
    output_path: str,
    num_top: int,
    num_random: int,
    exclude_inputs: tuple[str, ...],
    id_column: str,
    batch_size: int,
    seed: int,
    scratch_dir: str | None,
) -> None:
    click.echo(
        f"Sampling by prediction from {featurized_input} and {preprocessed_input}..."
    )

    identifier = Path(output_path).stem
    feature_cols = list(featurized)

    featurized_files = resolve_parquet_files(featurized_input)
    preprocessed_files = resolve_parquet_files(preprocessed_input)
    exclude_files = _exclusion_files(exclude_inputs, output_path)

    expected_state = {
        "num_top": num_top,
        "num_random": num_random,
        "feature_cols": feature_cols,
        "seed": seed,
    }
    manifest = _input_manifest(
        [*featurized_files, *preprocessed_files, *exclude_files, model_path],
        output_path,
        source_root,
        expected_state,
    )

    try:
        if _already_sampled(manifest, output_path):
            logger.info("Valid manifest found.", manifest=manifest.data)
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    total_rows = count_rows(featurized_files)
    preprocessed_rows = count_rows(preprocessed_files)
    if total_rows != preprocessed_rows:
        raise RuntimeError(
            f"Row count mismatch: {total_rows} featurized vs"
            f" {preprocessed_rows} preprocessed"
        )

    start_time = time.perf_counter()

    model = _load_model(model_path)
    valid_cols = _valid_columns(featurized_files[0])
    id_type = pq.ParquetFile(featurized_files[0]).schema_arrow.field(id_column).type
    excluded_ids = _load_excluded_ids(exclude_files, id_column, id_type)

    logger.info(
        "Scoring library with surrogate model",
        identifier=identifier,
        model_path=model_path,
        total_rows=total_rows,
        featurized=feature_cols,
        excluded_rows=0 if excluded_ids is None else len(excluded_ids),
    )
    scores = _score_all(
        model,
        featurized_files,
        feature_cols,
        valid_cols,
        id_column,
        excluded_ids,
        total_rows,
        batch_size,
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
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    _write_selection_via_staged_output(
        featurized_files,
        preprocessed_files,
        positions,
        Path(output_path),
        id_column,
        batch_size,
        scratch_dir,
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished prediction-based sampling",
        identifier=identifier,
        num_samples=len(positions),
        output_path=output_path,
    )
    click.echo("Done!")
