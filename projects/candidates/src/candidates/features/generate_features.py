# modules/local/generate_features/src/generate_features/generate_features.py

import json
import os
import sys
from concurrent.futures import Future, ProcessPoolExecutor

import click
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log
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


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()

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

    base = batch.drop_columns(["conformer", "smiles"])
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


def _marker_path(output_path: str, identifier: str) -> str:
    base_dir = os.path.dirname(output_path)
    return os.path.join(base_dir, f"_SUCCESS_{identifier}")


def _state_is_valid(
    output_path: str, num_rows: int, expected_fields: set[str], identifier: str
) -> bool:
    marker_path = _marker_path(output_path, identifier)
    if not os.path.exists(marker_path):
        return False
    try:
        with open(marker_path, "r") as f:
            data = json.load(f)
            return (
                data.get("num_rows") == num_rows
                and set(data.get("expected_fields", [])) == expected_fields
            )
    except Exception:
        return False


def _write_success_marker(
    output_path: str, num_rows: int, expected_fields: set[str], identifier: str
) -> None:
    marker_path = _marker_path(output_path, identifier)
    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
    with open(marker_path, "w") as f:
        json.dump({"num_rows": num_rows, "expected_fields": list(expected_fields)}, f)


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

    identifier = os.path.basename(input_path).replace(".parquet", "")

    parquet_file = pq.ParquetFile(input_path)
    num_rows = parquet_file.metadata.num_rows

    feature_generators = _build_feature_generators(features)
    expected_fields = _expected_schema_fields(
        parquet_file.schema_arrow, feature_generators
    )

    if _state_is_valid(output_path, num_rows, expected_fields, identifier):
        logger.info(
            "Features already valid, skipping generation",
            file=identifier,
            num_rows=num_rows,
            output_path=output_path,
        )
        click.echo("Done!")
        return

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

    _write_success_marker(output_path, num_rows, expected_fields, identifier)

    logger.info(
        "Finished generating features",
        file=identifier,
        num_rows=num_rows,
        output_path=output_path,
    )
    click.echo("Done!")
