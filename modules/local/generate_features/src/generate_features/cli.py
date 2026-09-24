# modules/local/generate_features/src/generate_features/generate_features.py

import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.cli import NumWorkers
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
from rdkit import rdBase
from rdkit.Chem import Mol, MolFromMolBlock

from generate_features.feature_generators import (
    FEATURE_GENERATOR_REGISTRY,
    FeatureGenerator,
)

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")


_WORKER_GENERATORS: dict[str, FeatureGenerator] | None = None


def _init_worker(generator_names: list[str]) -> None:
    global _WORKER_GENERATORS, _WORKER_GENERATOR_NAMES
    _WORKER_GENERATOR_NAMES = generator_names
    _WORKER_GENERATORS = {
        generator.name: generator
        for generator in _build_feature_generators(generator_names)
    }


def _build_feature_generators(generator_names: list[str]) -> list[FeatureGenerator]:
    return [FEATURE_GENERATOR_REGISTRY[name]() for name in generator_names]


def _chunk_list(input_list: list, size: int):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


def _generate_feature_chunk(
    generator_name: str, conformer_chunk: list[str]
) -> list[dict]:
    if _WORKER_GENERATORS is None:
        raise RuntimeError("worker not initialized: _WORKER_GENERATORS is None")
    generator = _WORKER_GENERATORS[generator_name]
    mols: list[Mol | None] = [
        MolFromMolBlock(conformer, removeHs=False) if conformer else None
        for conformer in conformer_chunk
    ]

    valid_indices = [i for i, mol in enumerate(mols) if mol is not None]
    valid_mols = [mols[i] for i in valid_indices]

    results: list[dict] = [generator.failure_result() for _ in mols]

    if valid_mols:
        valid_results = generator.generate_feature_batch(valid_mols)
        for index, result in zip(valid_indices, valid_results):
            results[index] = result

    return results


def _expected_schema_fields(
    input_schema: pa.Schema, feature_generators: list[FeatureGenerator]
) -> set[str]:
    field_names = set(input_schema.names)
    for generator in feature_generators:
        field_names.update(name for name, _ in generator.output_fields())
    return field_names


def _output_matches_expected(
    fs,
    output: str,
    expected_rows: int,
    expected_fields: set[str],
) -> bool:
    try:
        existing = pq.ParquetFile(output, filesystem=fs)
    except FileNotFoundError:
        return False

    if existing.metadata.num_rows != expected_rows:
        return False

    return set(existing.schema_arrow.names) == expected_fields


@click.command()
@click.option(
    "--input", type=str, required=True, help="Path to the input Parquet file."
)
@click.option(
    "--output", type=str, required=True, help="Path to the output Parquet file."
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read input and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option("--batch-size", default=10_000, type=int, help="Parquet read batch size.")
@click.option(
    "--chunk-size",
    default=50,
    type=int,
    help="Worker chunk size for the feature generation process pool.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@click.option(
    "--features",
    "-f",
    multiple=True,
    type=click.Choice(list(FEATURE_GENERATOR_REGISTRY), case_sensitive=False),
    default=list(FEATURE_GENERATOR_REGISTRY),
    show_default=True,
    help="Features to generate.",
)
def generate_features(
    input: str,
    output: str,
    use_blob_storage: bool,
    bucket: str,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    features: list[str],
):
    logger.info("generating features for %s", input)

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    input = f"s3://{bucket}/{input}" if use_blob_storage else input
    output = f"s3://{bucket}/{output}" if use_blob_storage else output

    parquet_file = pq.ParquetFile(input, filesystem=fs)
    num_rows = parquet_file.metadata.num_rows

    feature_generators = _build_feature_generators(features)
    expected_fields = _expected_schema_fields(
        parquet_file.schema_arrow, feature_generators
    )

    if _output_matches_expected(fs, output, num_rows, expected_fields):
        logger.info(
            "%s already exists with %d rows matching expected schema. Skipping.",
            output,
            num_rows,
        )
        return

    writer = None

    logger.info("processed 0 of %d", num_rows)

    with ProcessPoolExecutor(
        max_workers=num_workers,
        initializer=_init_worker,
        initargs=(features,),
        max_tasks_per_child=100,
    ) as executor:
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            conformers = batch["conformer"].to_pylist()
            chunks = list(_chunk_list(conformers, chunk_size))

            futures = {
                executor.submit(_generate_feature_chunk, generator.name, chunk): (
                    generator,
                    chunk_index,
                )
                for generator in feature_generators
                for chunk_index, chunk in enumerate(chunks)
            }

            results_by_generator: dict[str, list[list[dict] | None]] = {
                generator.name: [None] * len(chunks) for generator in feature_generators
            }

            for future in futures:
                generator, chunk_index = futures[future]
                results_by_generator[generator.name][chunk_index] = future.result()

            new_batch = batch.drop_columns(["conformer", "smiles"])
            for generator in feature_generators:
                chunk_results = results_by_generator[generator.name]
                if any(chunk_result is None for chunk_result in chunk_results):
                    raise RuntimeError(
                        f"missing chunk result(s) for generator '{generator.name}'"
                    )

                flattened = [
                    row
                    for chunk_result in chunk_results
                    if chunk_result is not None
                    for row in chunk_result
                ]

                for field_name, field_type in generator.output_fields():
                    column_values = [row[field_name] for row in flattened]
                    new_batch = new_batch.append_column(
                        field_name, pa.array(column_values, type=field_type)
                    )

            if writer is None:
                writer = pq.ParquetWriter(output, new_batch.schema, filesystem=fs)

            writer.write_batch(new_batch)
            logger.info("processed %d of %d", (i + 1) * batch_size, num_rows)

    if writer is not None:
        writer.close()
