# modules/local/preprocess_candidates/src/preprocess_candidates/preprocess.py
import gzip
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterator

import click
import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, RDLogger

from .steps import DescriptorsStep, MorganFingerprintStep, PainsStep, Step

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_LOG_INTERVAL = 5_000
_BATCH_SIZE = 10_000

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


def _results_to_frame(
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
                logger.warning(
                    "Step computation failed for catalog_id=%s: %s", catalog_id, exc
                )
                row["steps_ok"] = False
                row["error_reason"] = f"step_failed: {exc}"
                for step in _worker_steps:
                    row.update(step.failure_result())

        results.append(row)
    return results


def _preprocess(
    input_path: Path,
    output_path: Path,
    num_workers: int,
    steps: list[Step],
) -> None:
    logger.info(
        "starting preprocessing with %d workers, steps=%s",
        num_workers,
        [s.name for s in steps],
    )

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = _build_arrow_schema(steps)

    total_processed = 0
    next_log_at = _LOG_INTERVAL

    with pq.ParquetWriter(output_path, schema) as writer:
        with ProcessPoolExecutor(
            max_workers=num_workers, initializer=_init_worker, initargs=(steps,)
        ) as executor:
            iterator = _iter_smiles(input_path)
            batches = _batch(iterator, _BATCH_SIZE)

            for results in executor.map(_process_batch, batches):
                record_batch = _results_to_frame(results, schema)
                writer.write_batch(record_batch)

                total_processed += len(results)
                if total_processed >= next_log_at:
                    logger.info("Processed %d molecules...", total_processed)
                    next_log_at = total_processed + _LOG_INTERVAL

    logger.info("Finished preprocessing. Total processed: %d", total_processed)


def _build_pipeline() -> list[Step]:
    return [DescriptorsStep(), PainsStep(), MorganFingerprintStep(2, 1024)]


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
    "output_path",
    type=click.Path(writable=True),
    required=True,
    help="Path to save the output.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NUM_WORKERS,
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def preprocess(input_path: str, output_path: str, num_workers: int):
    steps = _build_pipeline()
    _preprocess(
        input_path=input_path,
        output_path=output_path,
        num_workers=num_workers,
        steps=steps,
    )
