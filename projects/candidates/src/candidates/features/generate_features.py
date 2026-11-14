# modules/local/generate_features/src/generate_features/generate_features.py


import datetime
import os
import time
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.cli import NumWorkers
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest
from rdkit import rdBase
from rdkit.Chem import Mol, MolFromMolBlock

from candidates.features.feature_generators import FEATURE_GENERATOR_REGISTRY
from candidates.features.feature_generators.feature_generator import (
    FeatureChunk,
    FeatureGenerator,
)

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"

MANIFEST_FILE_SUFFIX = ".manifest.json"

MAX_TASKS_PER_CHILD = 100

DROPPED_COLUMNS = ["conformer", "smiles"]

logger = get_lynceus_logger()

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")


_WORKER_GENERATORS: dict[str, FeatureGenerator] | None = None


def _input_manifest(
    input_path: str,
    output_path: str,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    manifest_path = Path(output_path).with_suffix(MANIFEST_FILE_SUFFIX)
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        [input_path], source_root
    )


def _already_generated(manifest: Manifest, output_path: str) -> bool:
    return Path(output_path).is_file() and manifest.exists_superset()


def _init_worker(generator_names: list[str]) -> None:
    global _WORKER_GENERATORS
    _WORKER_GENERATORS = {
        generator.name: generator
        for generator in _build_feature_generators(generator_names)
    }


def _build_feature_generators(generator_names: list[str]) -> list[FeatureGenerator]:
    return [FEATURE_GENERATOR_REGISTRY[name]() for name in generator_names]


def _chunk_list(input_list: list, size: int):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


def _parse_conformers(conformers: list[str]) -> list[Mol | None]:
    return [
        MolFromMolBlock(conformer, removeHs=False) if conformer else None
        for conformer in conformers
    ]


def _generate_feature_chunk(
    generator_name: str, conformer_chunk: list[str]
) -> FeatureChunk:
    if _WORKER_GENERATORS is None:
        raise RuntimeError("worker not initialized: _WORKER_GENERATORS is None")
    return _WORKER_GENERATORS[generator_name].generate_feature_chunk(
        _parse_conformers(conformer_chunk)
    )


def _submit_chunks(
    executor: ProcessPoolExecutor,
    feature_generators: list[FeatureGenerator],
    chunks: list[list[str]],
) -> dict[str, list[Future[FeatureChunk]]]:
    return {
        generator.name: [
            executor.submit(_generate_feature_chunk, generator.name, chunk)
            for chunk in chunks
        ]
        for generator in feature_generators
    }


def _process_batch(
    batch: pa.RecordBatch,
    feature_generators: list[FeatureGenerator],
    chunk_size: int,
    executor: ProcessPoolExecutor,
) -> pa.RecordBatch:
    chunks = list(_chunk_list(batch["conformer"].to_pylist(), chunk_size))
    pending = _submit_chunks(executor, feature_generators, chunks)

    base = batch.drop_columns(DROPPED_COLUMNS)
    arrays = list(base.columns)
    names = list(base.schema.names)

    for generator in feature_generators:
        results = [future.result() for future in pending.pop(generator.name)]
        for field_name, array in generator.to_columns(results):
            arrays.append(array)
            names.append(field_name)

    return pa.RecordBatch.from_arrays(arrays, names=names)


def _expected_schema_fields(
    input_schema: pa.Schema, feature_generators: list[FeatureGenerator]
) -> set[str]:
    field_names = set(input_schema.names)
    for generator in feature_generators:
        field_names.update(name for name, _ in generator.output_fields())
    return field_names


def _write_feature_file(
    input_path: str,
    output_file: Path,
    feature_generators: list[FeatureGenerator],
    features: list[str],
    batch_size: int,
    chunk_size: int,
    num_workers: int,
) -> None:
    parquet_file = pq.ParquetFile(input_path)
    num_rows = parquet_file.metadata.num_rows
    writer = None

    try:
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_init_worker,
            initargs=(features,),
            max_tasks_per_child=MAX_TASKS_PER_CHILD,
        ) as executor:
            for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
                new_batch = _process_batch(
                    batch, feature_generators, chunk_size, executor
                )

                if writer is None:
                    writer = pq.ParquetWriter(output_file, new_batch.schema)

                writer.write_batch(new_batch)
                del batch, new_batch

                logger.info(
                    "Processed batch",
                    batch_index=i + 1,
                    processed=min((i + 1) * batch_size, num_rows),
                    total_rows=num_rows,
                )
    finally:
        if writer is not None:
            writer.close()


def _generate_via_staged_output(
    input_path: str,
    output_path: Path,
    feature_generators: list[FeatureGenerator],
    features: list[str],
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    scratch_dir: str | None,
) -> None:
    with staged_output(
        output_path.parent,
        transfers=STAGED_OUTPUT_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        _write_feature_file(
            input_path,
            local_output / output_path.name,
            feature_generators,
            features,
            batch_size,
            chunk_size,
            num_workers,
        )


@click.command("generate_features")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to the input Parquet file.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Path to the output Parquet file.",
)
@click.option(
    "--batch-size",
    "batch_size",
    default=10_000,
    type=click.IntRange(min=1),
    show_default=True,
    help="Parquet read batch size.",
)
@click.option(
    "--chunk-size",
    "chunk_size",
    default=50,
    type=click.IntRange(min=1),
    show_default=True,
    help="Worker chunk size for the feature generation process pool.",
)
@click.option(
    "--num-workers",
    "num_workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@click.option(
    "--features",
    "-f",
    "features",
    multiple=True,
    type=click.Choice(list(FEATURE_GENERATOR_REGISTRY), case_sensitive=False),
    default=list(FEATURE_GENERATOR_REGISTRY),
    show_default=True,
    help="Features to generate.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the feature file before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def generate_features(
    source_root: Path,
    input_path: str,
    output_path: str,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    features: tuple[str, ...],
    scratch_dir: str | None,
) -> None:
    click.echo(f"Processing {input_path}...")

    feature_names = list(features)
    feature_generators = _build_feature_generators(feature_names)
    expected_fields = _expected_schema_fields(
        pq.ParquetFile(input_path).schema_arrow, feature_generators
    )

    expected_state = {
        "batch_size": batch_size,
        "chunk_size": chunk_size,
        "features": sorted(feature_names),
        "expected_fields": sorted(expected_fields),
    }
    manifest = _input_manifest(input_path, output_path, source_root, expected_state)

    try:
        if _already_generated(manifest, output_path):
            logger.info(
                "Valid manifest found. Features already generated.",
                manifest=manifest.data,
            )
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Generating features",
        source=input_path,
        output_path=output_path,
        source_root=str(source_root),
        workers=num_workers,
        features=feature_names,
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    _generate_via_staged_output(
        input_path,
        Path(output_path),
        feature_generators,
        feature_names,
        batch_size,
        chunk_size,
        num_workers,
        scratch_dir,
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info("Finished generating features", manifest=manifest.data)
    click.echo("Done!")


if __name__ == "__main__":
    generate_features()
