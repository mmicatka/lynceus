# modules/local/generate_features/src/generate_features/generate_features.py

import datetime
import json
import os
import time
from concurrent.futures import Future, ProcessPoolExecutor

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import get_lynceus_logger, wide_log
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


logger = get_lynceus_logger()

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")


_WORKER_GENERATORS: dict[str, FeatureGenerator] | None = None


class Manifest:
    def __init__(self, data: dict, filepath: str):
        self.data = data
        self.filepath = filepath

    def exists_superset(self) -> bool:
        if not os.path.exists(self.filepath):
            return False
        try:
            with open(self.filepath, "r") as f:
                saved_data = json.load(f)
            for key, value in self.data.items():
                if saved_data.get(key) != value:
                    return False
            return True
        except Exception:
            return False

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)


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


def _parse_conformers(conformers: list[str]) -> list[Mol | None]:
    return [
        MolFromMolBlock(conformer, removeHs=False) if conformer else None
        for conformer in conformers
    ]


def _generate_all_features_chunk(conformer_chunk: list[str]) -> dict[str, FeatureChunk]:
    """Worker function: parses molecules ONCE and runs all generators."""
    if _WORKER_GENERATORS is None:
        raise RuntimeError("worker not initialized: _WORKER_GENERATORS is None")

    # 1. Parse the chunk exactly once
    mols = _parse_conformers(conformer_chunk)

    # 2. Run all generators on the parsed molecules
    return {
        name: generator.generate_feature_chunk(mols)
        for name, generator in _WORKER_GENERATORS.items()
    }


def _submit_chunks(
    executor: ProcessPoolExecutor,
    chunks: list[list[str]],
) -> list[Future]:
    """Submit each chunk of strings to the executor exactly once."""
    return [executor.submit(_generate_all_features_chunk, chunk) for chunk in chunks]


def _process_batch(
    batch: pa.RecordBatch,
    feature_generators: list[FeatureGenerator],
    chunk_size: int,
    executor: ProcessPoolExecutor,
) -> pa.RecordBatch:
    chunks = list(_chunk_list(batch["conformer"].to_pylist(), chunk_size))

    # Submit chunks to the process pool
    pending_futures = _submit_chunks(executor, chunks)

    base = batch.drop_columns(["conformer", "smiles"])
    arrays = list(base.columns)
    names = list(base.schema.names)

    # Pre-allocate containers for the results of each generator
    gathered_results = {gen.name: [] for gen in feature_generators}

    # Gather results from all futures
    for future in pending_futures:
        chunk_result = future.result()
        for gen_name in gathered_results:
            gathered_results[gen_name].append(chunk_result[gen_name])

    # Convert the gathered feature chunks into PyArrow columns
    for generator in feature_generators:
        for field_name, array in generator.to_columns(gathered_results[generator.name]):
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


@click.command("generate_features")
@click.option(
    "--input",
    "input_path",
    type=str,
    required=True,
    help="Path to the input Parquet file.",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    required=True,
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
@wide_log(logger)
def generate_features(
    input_path: str,
    output_path: str,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    features: list[str],
):
    click.echo(f"Processing {input_path}...")

    key = os.path.basename(input_path).replace(".parquet", "")

    parquet_file = pq.ParquetFile(input_path)
    num_rows = parquet_file.metadata.num_rows

    feature_generators = _build_feature_generators(features)
    expected_fields = _expected_schema_fields(
        parquet_file.schema_arrow, feature_generators
    )

    manifest_data = {
        "input_path": input_path,
        "output_path": output_path,
        "num_rows": num_rows,
        "batch_size": batch_size,
        "chunk_size": chunk_size,
        "features": sorted(list(features)),
        "expected_fields": sorted(list(expected_fields)),
    }

    manifest_path = f"{output_path.rstrip('/')}.manifest.json"
    manifest = Manifest(data=manifest_data, filepath=manifest_path)

    try:
        if manifest.exists_superset():
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
        num_rows=num_rows,
        workers=num_workers,
        features=list(features),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = None

    start_time = time.perf_counter()

    with ProcessPoolExecutor(
        max_workers=num_workers,
        initializer=_init_worker,
        initargs=(features,),
        max_tasks_per_child=100,
    ) as executor:
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            new_batch = _process_batch(batch, feature_generators, chunk_size, executor)

            if writer is None:
                writer = pq.ParquetWriter(output_path, new_batch.schema)

            writer.write_batch(new_batch)
            del batch, new_batch

            logger.info(
                "Processed batch",
                batch_index=i + 1,
                processed=min((i + 1) * batch_size, num_rows),
                total_rows=num_rows,
            )

    if writer is not None:
        writer.close()

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished generating features",
        file=key,
        num_rows=num_rows,
        output_path=output_path,
    )
    click.echo("Done!")


if __name__ == "__main__":
    generate_features()
