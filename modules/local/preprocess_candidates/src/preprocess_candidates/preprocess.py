# modules/local/preprocess_candidates/src/preprocess_candidates/preprocess.py


import argparse
import gzip
import logging
import os
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, RDLogger

from preprocess_candidates.steps.descriptors import BasicDescriptorsStep

from .steps.step import Step, StepContext

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500

DEFAULT_PIPELINE_STEPS: list[Step] = [
    BasicDescriptorsStep(),
    # MorganFingerprintStep(radius=2, n_bits=2048),
    # CnsMpoStep(),
    # PainsFilterStep(),
    # ProtonationStateStep(ph_min=6.4, ph_max=8.4),
    # ConformerGenerateStep(random_seed=1000),
]


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
    ]
    for step in steps:
        for name, dtype in step.output_fields():
            fields.append(pa.field(name, dtype))
    return pa.schema(fields)


def _preprocess_record(record: tuple[str, str]) -> dict[str, Any]:
    smiles, catalog_id = record
    mol = Chem.MolFromSmiles(smiles)

    row: dict[str, Any] = {
        "catalog_id": catalog_id,
        "smiles": smiles,
        "parse_ok": mol is not None,
    }

    if mol is None:
        for step in _worker_steps:
            row.update(step.failure_result())
        return row

    ctx = StepContext(catalog_id=catalog_id, smiles=smiles, mol=mol)
    for step in _worker_steps:
        try:
            row.update(step.compute(ctx))
        except Exception as exc:
            logger.warning(
                "step %s failed for catalog_id=%s: %s", step.name, catalog_id, exc
            )
            row.update(step.failure_result())

    return row


def _iter_smiles(path: Path) -> Iterator[tuple[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.lower().startswith("smiles"):
                continue
            parts = line.split(None, 2)
            if len(parts) >= 2:
                yield parts[0], parts[1]


def _batch(iterator: Iterator, size: int) -> Iterator[list]:
    batch = []
    for item in iterator:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _results_to_frame(
    results: list[dict[str, Any]], schema: pa.Schema
) -> pa.RecordBatch:
    return pa.RecordBatch.from_pylist(results, schema=schema)


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

    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = _build_arrow_schema(steps)

    n_written = 0
    n_parse_failed = 0

    log_interval = 50_000
    next_log_threshold = log_interval

    writer = None

    try:
        with Pool(
            processes=num_workers,
            initializer=_init_worker,
            initargs=(steps,),
        ) as pool:
            for chunk_results in _batch(
                pool.imap(
                    _preprocess_record, _iter_smiles(input_path), chunksize=_CHUNK_SIZE
                ),
                _CHUNK_SIZE,
            ):
                n_parse_failed += sum(1 for r in chunk_results if not r["parse_ok"])
                batch = _results_to_frame(chunk_results, schema)
                if writer is None:
                    writer = pq.ParquetWriter(output_path, schema, compression="zstd")
                writer.write_batch(batch)
                n_written += len(chunk_results)

                if n_written >= next_log_threshold:
                    logger.info(
                        "Progress: processed %d records (parse failed: %d)",
                        n_written,
                        n_parse_failed,
                    )
                    next_log_threshold += log_interval
    finally:
        if writer is not None:
            writer.close()

    if n_parse_failed:
        logger.warning("%d records failed SMILES parsing", n_parse_failed)
    logger.info("Wrote %d records to %s", n_written, output_path)


def _parse_num_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to a .smi.gz file (SMILES<TAB>catalog_id per line)",
    )
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the output .parquet file",
    )
    p.add_argument(
        "--num-workers", metavar="N|auto", default="auto", type=_parse_num_workers
    )
    p.add_argument("--morgan-radius", type=int, default=2)
    p.add_argument("--morgan-n-bits", type=int, default=2048)
    p.add_argument("--ph-min", type=float, default=6.4)
    p.add_argument("--ph-max", type=float, default=8.4)
    p.add_argument("--conformer-random-seed", type=int, default=1000)
    p.add_argument(
        "--skip-conformers",
        action="store_true",
        help="Run fingerprinting/descriptor steps only, skip conformer generation.",
    )

    return p.parse_args()


def _build_pipeline(args: argparse.Namespace) -> list[Step]:
    return [
        # BasicDescriptorsStep(),
        # MorganFingerprintStep(radius=args.morgan_radius, n_bits=args.morgan_n_bits),
        # CnsMpoStep(),
        # PainsFilterStep(),
        # ProtonationStateStep(ph_min=args.ph_min, ph_max=args.ph_max),
        # ConformerGenerateStep(random_seed=args.conformer_random_seed),
    ]


def preprocess():
    args = _parse_args()
    steps = _build_pipeline(args)
    _preprocess(
        input_path=args.input,
        output_path=args.output,
        num_workers=args.num_workers,
        steps=steps,
    )
