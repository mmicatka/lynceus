# projects/surrogate-model/src/surrogate_model/cli/sample.py


import datetime
import time
from pathlib import Path

import click
import numpy as np
import pyarrow.parquet as pq
from lynceus_core.io.staged_io import staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

from surrogate_model.common.io import (
    aligned_chunks,
    count_rows,
    resolve_parquet_files,
    select_aligned,
    verify_written,
)

DEFAULT_RANDOM_SEED = 1000

PARQUET_PATTERN = "*.parquet"
CONFORMER_COLUMN = "conformer"
COMPRESSION = "zstd"
DEFAULT_BATCH_SIZE = 50_000

STAGED_IO_TRANSFERS = 4

RUN_TIME_KEY = "run_time"

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


def _select_positions(
    total_rows: int, num_samples: int, seed: int | None
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(total_rows, size=num_samples, replace=False))


def _write_sample(
    featurized_files: list[str],
    preprocessed_files: list[str],
    positions: np.ndarray,
    output_file: str,
    id_column: str,
    batch_size: int,
) -> None:
    writer: pq.ParquetWriter | None = None
    offset = 0
    try:
        for featurized, preprocessed in aligned_chunks(
            featurized_files, preprocessed_files, id_column, batch_size
        ):
            end = offset + featurized.num_rows
            lo, hi = np.searchsorted(positions, [offset, end])
            selected = select_aligned(
                featurized, preprocessed, positions[lo:hi] - offset, id_column
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


def _sample_via_staged_io(
    featurized_files: list[str],
    preprocessed_files: list[str],
    positions: np.ndarray,
    output_path: Path,
    id_column: str,
    batch_size: int,
    scratch_dir: str | None,
) -> None:
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

        _write_sample(
            local_featurized,
            local_preprocessed,
            positions,
            str(local_file),
            id_column,
            batch_size,
        )
        verify_written(str(local_file), len(positions))


@click.command("sample_aligned")
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
    help="featurized parquet file, glob pattern, or folder of parquet files.",
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
def sample_surrogate_candidates(
    source_root: Path,
    featurized_input: str,
    preprocessed_input: str,
    output_path: str,
    num_samples: int,
    id_column: str,
    batch_size: int,
    seed: int,
    scratch_dir: str | None,
) -> None:
    click.echo(
        f"Processing aligned samples from {featurized_input}"
        f" and {preprocessed_input}..."
    )

    identifier = Path(output_path).stem

    featurized_files = resolve_parquet_files(featurized_input)
    preprocessed = resolve_parquet_files(preprocessed_input)

    expected_state = {"num_samples": num_samples, "seed": seed}
    manifest = _input_manifest(
        [*featurized_files, *preprocessed],
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
    preprocessed_rows = count_rows(preprocessed)
    if total_rows != preprocessed_rows:
        raise RuntimeError(
            f"Row count mismatch: {total_rows} featurized vs"
            f" {preprocessed_rows} preprocessed"
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
        featurized_source=featurized_input,
        preprocessed_source=preprocessed_input,
        num_featurized_files=len(featurized_files),
        num_preprocessed_files=len(preprocessed),
        identifier=identifier,
        total_rows=total_rows,
        num_samples=effective_samples,
        output_path=output_path,
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    positions = _select_positions(total_rows, effective_samples, seed)

    _sample_via_staged_io(
        featurized_files,
        preprocessed,
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
        "Finished aligned position sampling",
        identifier=identifier,
        num_samples=effective_samples,
        output_path=output_path,
        elapsed_time=elapsed_time,
    )
    click.echo("Done!")
