# projects/surrogate-model/src/surrogate_model/cli/train.py


import datetime
import time
from collections.abc import Sequence
from pathlib import Path

import click
from lynceus_core.cli import PATH_SEPARATOR, split_paths
from lynceus_core.logging import get_lynceus_logger, wide_log

from surrogate_model.common.cli import features_option, model_type_option
from surrogate_model.common.io import save_model_staged
from surrogate_model.common.manifest import input_manifest, is_up_to_date
from surrogate_model.common.metrics import DEFAULT_EVAL_PERCENTS
from surrogate_model.common.model import ModelType
from surrogate_model.common.threshold import get_validation_threshold
from surrogate_model.common.training import train_and_evaluate

RANDOM_SEED = 1000
RUN_TIME_KEY = "run_time"

logger = get_lynceus_logger()


def _expected_state(
    features: list[str],
    threshold: float,
    eval_percents: Sequence[float],
    model_type: ModelType,
) -> dict:
    return {
        "features": list(features),
        "threshold": threshold,
        "seed": RANDOM_SEED,
        "eval_percents": list(eval_percents),
        "model_type": str(model_type),
    }


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
    help=f"{PATH_SEPARATOR}-separated paths to the input featurized files.",
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
    help="Path to the input featurized file.",
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
@model_type_option
@features_option
@click.option(
    "--eval-percents",
    "eval_percents",
    type=click.FloatRange(min=0.0, min_open=True, max=1.0),
    multiple=True,
    default=DEFAULT_EVAL_PERCENTS,
    show_default=True,
    help="Fractions (in (0, 1]) of top predictions to evaluate metrics at.",
)
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
    features: tuple[str, ...],
    model_path: str,
    model_type: ModelType,
    eval_percents: tuple[float, ...],
    scratch_dir: str | None,
) -> None:
    click.echo(
        f"Training {model_type} surrogate model using"
        f" {len(train_features_paths)} feature files..."
    )

    feature_cols = list(features)
    threshold = get_validation_threshold(validation_labels_path)
    logger.info("threshold", threshold=threshold)

    manifest = input_manifest(
        [
            *train_features_paths,
            *train_labels_paths,
            validation_features_path,
            validation_labels_path,
        ],
        model_path,
        source_root,
        _expected_state(feature_cols, threshold, eval_percents, model_type),
    )

    if is_up_to_date(manifest, model_path):
        logger.info("Valid manifest found.", manifest=manifest.data)
        click.echo("Done!")
        return

    logger.info(
        "Training surrogate model",
        manifest=manifest.data,
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    model, results = train_and_evaluate(
        train_features_paths=train_features_paths,
        train_labels_paths=train_labels_paths,
        validation_features_path=validation_features_path,
        validation_labels_path=validation_labels_path,
        features=feature_cols,
        threshold=threshold,
        random_seed=RANDOM_SEED,
        model_type=model_type,
        eval_percents=eval_percents,
    )

    save_model_staged(model, model_path, scratch_dir)

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.data.update(results)
    manifest.save()

    click.echo("Done!")
