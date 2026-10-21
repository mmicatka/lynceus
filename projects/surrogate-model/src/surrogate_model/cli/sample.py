# projects/surrogate-model/src/surrogate_model/cli/sample.py

import os
from pathlib import Path

import click
import numpy as np
import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger, wide_log

from surrogate_model.common.io import (
    aligned_chunks,
    count_rows,
    manifest_valid,
    resolve_parquet_files,
    select_aligned,
    verify_written,
    write_manifest,
)

PARQUET_PATTERN = "*.parquet"
MARKER_SUFFIX = ".success"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000


logger = get_lynceus_logger()


def _select_positions(
    total_rows: int, num_samples: int, seed: int | None
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(total_rows, size=num_samples, replace=False))


def _write_sample(
    features_files: list[str],
    conformers_files: list[str],
    positions: np.ndarray,
    output_file: str,
    id_column: str,
    batch_size: int,
) -> None:
    writer: pq.ParquetWriter | None = None
    offset = 0
    try:
        for features, conformers in aligned_chunks(
            features_files, conformers_files, id_column, batch_size
        ):
            end = offset + features.num_rows
            lo, hi = np.searchsorted(positions, [offset, end])
            selected = select_aligned(
                features, conformers, positions[lo:hi] - offset, id_column
            )
            if writer is None:
                writer = pq.ParquetWriter(
                    output_file, selected.schema, compression=COMPRESSION
                )
            writer.write_table(selected)
            offset = end
    finally:
        if writer is not None:
            writer.close()


@click.command("sample_aligned")
@click.option(
    "--features-input",
    "features_input",
    required=True,
    type=str,
    help="Features parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--conformers-input",
    "conformers_input",
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
    "--num-samples",
    "num_samples",
    required=True,
    type=click.IntRange(min=1),
    help="Total number of samples to pull.",
)
@click.option(
    "--id-column",
    "id_column",
    default="id",
    show_default=True,
    type=str,
    help="ID column used to verify row alignment.",
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
    default=None,
    type=int,
    help="Seed for reproducible sampling.",
)
@wide_log(logger)
def sample_candidates(
    features_input: str,
    conformers_input: str,
    output_path: str,
    num_samples: int,
    id_column: str,
    batch_size: int,
    seed: int | None,
) -> None:
    click.echo(
        f"Processing aligned samples from {features_input} and {conformers_input}..."
    )

    identifier = Path(output_path).stem

    features_files = resolve_parquet_files(features_input)
    conformers_files = resolve_parquet_files(conformers_input)

    manifest = {
        "features_files": features_files,
        "conformers_files": conformers_files,
        "num_samples": num_samples,
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

    effective_samples = min(num_samples, total_rows)
    if effective_samples < num_samples:
        logger.warning(
            "Requested more samples than available rows, returning all rows",
            identifier=identifier,
            requested=num_samples,
            available=total_rows,
        )

    logger.info(
        "Executing aligned position sampling",
        features_source=features_input,
        conformers_source=conformers_input,
        num_features_files=len(features_files),
        num_conformers_files=len(conformers_files),
        identifier=identifier,
        total_rows=total_rows,
        num_samples=effective_samples,
        output_path=output_path,
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    positions = _select_positions(total_rows, effective_samples, seed)

    _write_sample(
        features_files=features_files,
        conformers_files=conformers_files,
        positions=positions,
        output_file=output_path,
        id_column=id_column,
        batch_size=batch_size,
    )

    verify_written(output_path, num_samples)
    write_manifest(manifest_path, manifest)

    logger.info(
        "Finished aligned position sampling",
        identifier=identifier,
        num_samples=effective_samples,
        output_path=output_path,
    )
    click.echo("Done!")
