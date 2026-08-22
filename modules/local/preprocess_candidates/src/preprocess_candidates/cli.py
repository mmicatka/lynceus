# modules/local/preprocess_candidates/src/preprocess_candidates/preprocess.py

import gzip
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterator

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from rdkit import Chem, RDLogger

from .steps import (
    ConformersStep,
    DescriptorsStep,
    MorganFingerprintStep,
    PainsStep,
    Step,
)

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_LOG_INTERVAL = 1_000
_BATCH_SIZE = 1_000

_worker_steps: list[Step] = []


def _init_worker(steps: list[Step]) -> None:
    global _worker_steps
    _worker_steps = steps
    for step in _worker_steps:
        step.init_worker()


def _build_arrow_schema(steps: list[Step]) -> pa.Schema:
    fields = [
        pa.field("catalog_id", pa.string()),
        pa.field("smiles", pa.string()),
        pa.field("parse_ok", pa.bool_()),
        pa.field("steps_ok", pa.bool_()),
        pa.field("error_reason", pa.string()),
    ]
    for step in steps:
        for name, dtype in step.output_fields():
            fields.append(pa.field(name, dtype))
    return pa.schema(fields)


def _count_smiles(path: Path) -> int:
    count = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.lower().startswith("smiles"):
                continue
            if len(line.split(None, 2)) >= 2:
                count += 1
    return count


def _iter_smiles(path: Path) -> Iterator[tuple[str, str]]:
    """Yields (smiles, catalog_id) pairs from a whitespace-delimited SMILES file."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.lower().startswith("smiles"):
                continue
            parts = line.split(None, 2)
            if len(parts) >= 2:
                smiles, catalog_id = parts[0], parts[1]
                yield smiles, catalog_id
            else:
                logger.warning(
                    "Skipping malformed line (expected 'smiles id'): %r", line
                )


def _results_to_batch(
    results: list[dict[str, Any]], schema: pa.Schema
) -> pa.RecordBatch:
    return pa.RecordBatch.from_pylist(results, schema=schema)


def _batch(iterator: Iterator, size: int) -> Iterator[list]:
    batch = []
    for item in iterator:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _process_batch(batch: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Worker function to process a batch of molecules."""
    results = []
    for smiles, catalog_id in batch:
        row = {
            "catalog_id": catalog_id,
            "smiles": smiles,
            "parse_ok": True,
            "steps_ok": True,
            "error_reason": "",
        }
        mol = Chem.MolFromSmiles(smiles)

        if mol is None:
            row["parse_ok"] = False
            row["steps_ok"] = False
            row["error_reason"] = "rdkit_parse_failed"
            for step in _worker_steps:
                row.update(step.failure_result())
        else:
            try:
                for step in _worker_steps:
                    out = step.compute(mol)
                    if out:
                        row.update(out)
            except Exception as exc:
                row["steps_ok"] = False
                row["error_reason"] = f"step_failed: {exc}"
                for step in _worker_steps:
                    row.update(step.failure_result())

        results.append(row)
    return results


def _preprocess(
    input_path: Path,
    num_workers: int,
    steps: list[Step],
) -> pa.Table:
    input_path = Path(input_path)

    logger.info("Counting total molecules in %s...", input_path.name)
    total_molecules = _count_smiles(input_path)

    logger.info(
        "starting preprocessing %d molecules with %d workers, steps=%s",
        total_molecules,
        num_workers,
        [s.name for s in steps],
    )

    schema = _build_arrow_schema(steps)

    total_processed = 0
    next_log_at = _LOG_INTERVAL
    record_batches: list[pa.RecordBatch] = []

    with ProcessPoolExecutor(
        max_workers=num_workers, initializer=_init_worker, initargs=(steps,)
    ) as executor:
        iterator = _iter_smiles(input_path)
        batches = _batch(iterator, _BATCH_SIZE)

        for results in executor.map(_process_batch, batches):
            record_batches.append(_results_to_batch(results, schema))

            total_processed += len(results)
            if total_processed >= next_log_at:
                logger.info(
                    "Processed %d of %d molecules...",
                    total_processed,
                    total_molecules,
                )
                next_log_at = total_processed + _LOG_INTERVAL

    if total_processed == 0:
        logger.error(
            "no molecules were processed from %s; refusing to write empty output",
            input_path,
        )
        sys.exit(1)

    logger.info(
        "Finished preprocessing. Processed %d of %d molecules.",
        total_processed,
        total_molecules,
    )

    return pa.Table.from_batches(record_batches, schema=schema)


def _build_pipeline(morgan_radius: int, morgan_n_bits: int, seed: int) -> list[Step]:
    return [
        DescriptorsStep(),
        PainsStep(),
        MorganFingerprintStep(morgan_radius, morgan_n_bits),
        ConformersStep(seed=seed),
    ]


def _write_local_parquet(table: pa.Table, output: str):
    pq.write_table(table, output)


class NumWorkersType(click.ParamType):
    name = "num_workers"

    def convert(self, value, param, ctx):
        val_str = str(value).lower().strip()
        if val_str == "auto":
            return os.cpu_count() or 1
        try:
            n = int(val_str)
            if n < 1:
                self.fail("workers must be >= 1", param, ctx)
            return n
        except ValueError:
            self.fail(
                f"'{value}' is not 'auto' or a valid positive integer", param, ctx
            )


NUM_WORKERS = NumWorkersType()


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to the input file.",
)
@click.option(
    "--output",
    "output",
    type=str,
    required=True,
    help="Output Parquet file.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NUM_WORKERS,
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@click.option(
    "--seed",
    default=1000,
    type=int,
    show_default=True,
    help="Random seed.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output Parquet file..",
)
@click.option("--bucket", type=str, default="lynceus", help="Output bucket name")
def preprocess(
    input_path: str,
    output: str,
    num_workers: int,
    seed: int,
    use_blob_storage: bool,
    bucket: str,
):
    steps = _build_pipeline(2, 1024, seed)

    table: pa.Table = _preprocess(
        input_path=input_path,
        num_workers=num_workers,
        steps=steps,
    )

    if use_blob_storage:
        logger.info("using blob storage...")
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        export_parquet(conn, table, bucket, output)
    else:
        _write_local_parquet(table, output)
