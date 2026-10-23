# projects/surrogate-model/src/surrogate_model/cli/prepare_validation.py


import click
import polars as pl
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

from surrogate_model.common.data import AFFINITY_COLUMN_NAME

logger = get_lynceus_logger()

RANDOM_SEED = 1000


@click.command()
@click.option(
    "--validation-path",
    "validation_path",
    type=str,
    required=True,
    help="Path to the validation docking results.",
)
@click.option(
    "--active-percentile",
    type=float,
    default=None,
    help="Affinity cutoff (kcal/mol) defining active. ",
)
@wide_log(logger)
def prepare_validation(
    validation_path: str,
    active_percentile: float,
):
    click.echo(f"Preparing validation from {validation_path}...")

    manifest_data = {
        "validation_path": validation_path,
        "active_percentile": active_percentile,
    }

    manifest_path = f"{validation_path}.manifest.json"
    target_manifest = Manifest(data=manifest_data, filepath=manifest_path)
    disk_manifest = Manifest(filepath=manifest_path)

    if disk_manifest.exists():
        try:
            disk_manifest.load()
            if target_manifest <= disk_manifest:
                logger.info(
                    "Validation already valid, skipping generation",
                    manifest=disk_manifest,
                )
                click.echo("Done!")
                return
        except Exception as e:
            logger.warning(
                "Failed to load existing manifest, re-generating.", error=str(e)
            )

    df = pl.read_parquet(validation_path, columns=[AFFINITY_COLUMN_NAME])

    negatives_df = df.filter(pl.col(AFFINITY_COLUMN_NAME) < 0)

    if negatives_df.height == 0:
        raise ValueError(
            f"No negative values found in column '{AFFINITY_COLUMN_NAME}'."
        )

    q = active_percentile / 100.0

    threshold = negatives_df.select(pl.col(AFFINITY_COLUMN_NAME).quantile(q)).item()
    num_active = negatives_df.filter(pl.col(AFFINITY_COLUMN_NAME) <= threshold).height

    target_manifest.data = {
        **manifest_data,
        "threshold": threshold,
        "num_samples": negatives_df.height,
        "num_active": num_active,
    }

    target_manifest.save()

    click.echo("Done!")
