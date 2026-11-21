# projects/surrogate-model/src/surrogate_model/cli/sample.py


import datetime
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

import click
import joblib
from lynceus_core.io.staged_io import staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log

from surrogate_model.common.cli import features_option
from surrogate_model.common.io import (
    DEFAULT_BATCH_SIZE,
    count_rows,
    resolve_parquet_files,
    verify_written,
    write_aligned_selection,
)
from surrogate_model.common.manifest import input_manifest, is_up_to_date
from surrogate_model.common.model import ProbabilisticClassifier
from surrogate_model.common.selection import (
    Selection,
    SelectionParams,
    exclusion_files,
    id_column_type,
    load_excluded_ids,
    select_positions,
)

DEFAULT_RANDOM_SEED = 1000

STAGED_IO_TRANSFERS = 4

RUN_TIME_KEY = "run_time"


logger = get_lynceus_logger()


def _require_consistent_mode(
    model_path: str | None, num_top: int, num_random: int
) -> None:
    if num_top > 0 and model_path is None:
        raise click.UsageError("--num-top requires --model.")
    if model_path is not None and num_top == 0:
        raise click.UsageError("--model requires --num-top greater than 0.")
    if num_top + num_random == 0:
        raise click.UsageError(
            "At least one of --num-top and --num-random must be positive."
        )


def _load_model(model_path: str | None) -> ProbabilisticClassifier | None:
    return None if model_path is None else joblib.load(model_path)


def _expected_state(
    params: SelectionParams, feature_cols: list[str], model_path: str | None
) -> dict:
    state: dict = {
        "num_top": params.num_top,
        "num_random": params.num_random,
        "seed": params.seed,
    }
    if model_path is not None:
        state["feature_cols"] = feature_cols
    return state


def _manifest_sources(
    featurized_files: list[str],
    preprocessed_files: list[str],
    exclude_files: list[str],
    model_path: str | None,
) -> list[str]:
    model_files = [] if model_path is None else [model_path]
    return [*featurized_files, *preprocessed_files, *exclude_files, *model_files]


def _aligned_row_count(
    featurized_files: list[str], preprocessed_files: list[str]
) -> int:
    featurized_rows = count_rows(featurized_files)
    preprocessed_rows = count_rows(preprocessed_files)
    if featurized_rows != preprocessed_rows:
        raise RuntimeError(
            f"Row count mismatch: {featurized_rows} featurized vs"
            f" {preprocessed_rows} preprocessed"
        )
    return featurized_rows


def _stage_and_write(
    featurized_files: list[str],
    preprocessed_files: list[str],
    output_path: Path,
    select: Callable[..., Selection],
    params: SelectionParams,
    scratch_dir: str | None,
) -> Selection:
    all_inputs = [Path(f) for f in (*featurized_files, *preprocessed_files)]
    split_idx = len(featurized_files)

    with staged_io(
        all_inputs,
        output_path.parent,
        transfers=STAGED_IO_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as (local_inputs, local_output):
        local_featurized = [str(p) for p in local_inputs[:split_idx]]
        local_preprocessed = [str(p) for p in local_inputs[split_idx:]]
        local_file = local_output / output_path.name

        selection = select(featurized_files=local_featurized)
        write_aligned_selection(
            featurized_files=local_featurized,
            preprocessed_files=local_preprocessed,
            positions=selection.positions,
            output_file=str(local_file),
            id_column=params.id_column,
            batch_size=params.batch_size,
        )
        verify_written(str(local_file), len(selection.positions))
    return selection


def _warn_shortfalls(
    identifier: str, params: SelectionParams, selection: Selection
) -> None:
    if len(selection.top) < params.num_top:
        logger.warning(
            "Fewer scored rows than requested top, keeping all",
            identifier=identifier,
            requested=params.num_top,
            available=selection.eligible_total,
        )
    if len(selection.random) < params.num_random:
        logger.warning(
            "Fewer remaining rows than requested random, keeping all",
            identifier=identifier,
            requested=params.num_random,
            available=selection.remaining_total,
        )


@click.command("sample")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option(
    "--featurized-input",
    "featurized_input",
    required=True,
    type=str,
    help="Featurized parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--preprocessed-input",
    "preprocessed_input",
    required=True,
    type=str,
    help="Conformer parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output parquet file path.",
)
@click.option(
    "--num-random",
    "num_random",
    required=True,
    type=click.IntRange(min=0),
    help="Number of uniformly sampled rows to add from the eligible rows.",
)
@click.option(
    "--num-top",
    "num_top",
    default=0,
    show_default=True,
    type=click.IntRange(min=0),
    help="Number of highest-scoring rows to keep. Requires --model.",
)
@click.option(
    "--model",
    "model_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Saved LightGBM model (.joblib). Required with --num-top.",
)
@features_option
@click.option(
    "--exclude-input",
    "exclude_inputs",
    multiple=True,
    type=str,
    help="Parquet file(s) or glob of previously sampled rows to exclude by id. "
    "Repeatable.",
)
@click.option(
    "--id-column",
    "id_column",
    default="id",
    show_default=True,
    type=str,
    help="ID column used to verify row alignment and apply exclusions.",
)
@click.option(
    "--batch-size",
    "batch_size",
    default=DEFAULT_BATCH_SIZE,
    show_default=True,
    type=click.IntRange(min=1),
    help="Rows read per chunk from each input.",
)
@click.option(
    "--seed",
    "seed",
    default=DEFAULT_RANDOM_SEED,
    type=int,
    help="Seed for reproducible sampling.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for staging input and output files "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def sample_candidates(
    source_root: Path,
    featurized_input: str,
    preprocessed_input: str,
    output_path: str,
    num_random: int,
    num_top: int,
    model_path: str | None,
    features: tuple[str, ...],
    exclude_inputs: tuple[str, ...],
    id_column: str,
    batch_size: int,
    seed: int,
    scratch_dir: str | None,
) -> None:
    _require_consistent_mode(model_path, num_top, num_random)
    click.echo(f"Sampling from {featurized_input} and {preprocessed_input}...")

    identifier = Path(output_path).stem
    feature_cols = list(features)
    params = SelectionParams(
        num_top=num_top,
        num_random=num_random,
        seed=seed,
        id_column=id_column,
        batch_size=batch_size,
    )

    featurized_files = resolve_parquet_files(featurized_input)
    preprocessed_files = resolve_parquet_files(preprocessed_input)
    exclude_files = exclusion_files(exclude_inputs, output_path)

    manifest = input_manifest(
        _manifest_sources(
            featurized_files, preprocessed_files, exclude_files, model_path
        ),
        output_path,
        source_root,
        _expected_state(params, feature_cols, model_path),
    )

    if is_up_to_date(manifest, output_path):
        logger.info("Valid manifest found.", manifest=manifest.data)
        click.echo("Done!")
        return

    total_rows = _aligned_row_count(featurized_files, preprocessed_files)

    start_time = time.perf_counter()

    excluded_ids = load_excluded_ids(
        exclude_files, id_column, id_column_type(featurized_files[0], id_column)
    )

    logger.info(
        "Selecting sample",
        identifier=identifier,
        model_path=model_path,
        total_rows=total_rows,
        num_top=num_top,
        num_random=num_random,
        featurized=feature_cols if model_path is not None else [],
        excluded_rows=0 if excluded_ids is None else len(excluded_ids),
        output_path=output_path,
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    select = partial(
        select_positions,
        model=_load_model(model_path),
        feature_cols=feature_cols,
        excluded_ids=excluded_ids,
        total_rows=total_rows,
        params=params,
    )
    selection = _stage_and_write(
        featurized_files,
        preprocessed_files,
        Path(output_path),
        select,
        params,
        scratch_dir,
    )
    _warn_shortfalls(identifier, params, selection)

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished sampling",
        identifier=identifier,
        num_top=len(selection.top),
        num_random=len(selection.random),
        output_path=output_path,
        elapsed_time=elapsed_time,
    )
    click.echo("Done!")
