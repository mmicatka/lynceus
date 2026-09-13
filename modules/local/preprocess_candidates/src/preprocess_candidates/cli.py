# modules/local/preprocess_candidates/src/preprocess_candidates/cli.py


import contextlib
import gzip
import itertools
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterator

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from pyarrow.fs import FileType, LocalFileSystem, S3FileSystem
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem

from preprocess_candidates.steps.conformers_gpu import ConformersGPUStep

from .steps import (
    Step,
)

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

_LOG_INTERVAL = 1000

_worker_steps: list[Step] = []


@contextlib.contextmanager
def _suppress_native_stderr():
    stderr_fd = 2
    saved_fd = os.dup(stderr_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(devnull_fd)
        os.close(saved_fd)


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
    rows = []
    parsed_mols: list[Chem.Mol | None] = []

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
        rows.append(row)
        parsed_mols.append(mol)

    for step in _worker_steps:
        live_indices = [
            i
            for i, (row, mol) in enumerate(zip(rows, parsed_mols))
            if row["steps_ok"] and mol is not None
        ]
        if not live_indices:
            continue

        live_mols = [parsed_mols[i] for i in live_indices]
        try:
            outs = step.compute_batch(live_mols)
        except Exception as exc:
            for i in live_indices:
                rows[i]["steps_ok"] = False
                rows[i]["error_reason"] = f"step_failed: {exc}"
                rows[i].update(step.failure_result())
            continue

        for i, out in zip(live_indices, outs):
            if out is None:
                rows[i]["steps_ok"] = False
                rows[i]["error_reason"] = "step_failed"
                rows[i].update(step.failure_result())
            else:
                rows[i].update(out)

    return rows


def _preprocess(
    input_path: Path,
    num_workers: int,
    batch_size: int,
    steps: list[Step],
    target_path: str,
    filesystem: Any,
) -> None:
    start_time = time.perf_counter()

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

    path_obj = Path(target_path)
    temp_path = str(path_obj.with_name(f".{path_obj.name}"))

    logger.info("Streaming directly to temporary path: %s", temp_path)

    with pq.ParquetWriter(temp_path, schema, filesystem=filesystem) as writer:
        with ProcessPoolExecutor(
            max_workers=num_workers, initializer=_init_worker, initargs=(steps,)
        ) as executor:
            iterator = _iter_smiles(input_path)
            batches = _batch(iterator, batch_size)

            for results in executor.map(_process_batch, batches):
                batch_data = _results_to_batch(results, schema)
                writer.write_batch(batch_data)

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

    logger.info("Finished processing. Renaming %s -> %s", temp_path, target_path)

    filesystem.move(temp_path, target_path)

    logger.info("Rename complete.")

    elapsed_time = time.perf_counter() - start_time
    mols_per_sec = total_processed / elapsed_time if elapsed_time > 0 else 0

    logger.info(
        "Processed %d molecules in %.2f seconds (%.2f mol/s)",
        total_processed,
        elapsed_time,
        mols_per_sec,
    )


# def _build_pipeline(morgan_radius: int, morgan_n_bits: int, seed: int) -> list[Step]:
#     return [
#         # DescriptorsStep(),
#         # PainsStep(),
#         # MorganFingerprintStep(morgan_radius, morgan_n_bits),
#         # ConformersCPUStep(seed=seed),
#         ConformersGPUStep(seed=seed)
#     ]


def _build_pipeline(
    seed: int,
    embed_hardware_options_path: Path | None = None,
    mmff_hardware_options_path: Path | None = None,
) -> list[Step]:
    return [
        ConformersGPUStep(
            seed=seed,
            embed_hardware_options_path=embed_hardware_options_path,
            mmff_hardware_options_path=mmff_hardware_options_path,
        )
    ]


def _sample_mols_for_tuning(
    input_path: Path, sample_size: int, seed: int
) -> list[Chem.Mol]:
    mols: list[Chem.Mol] = []
    for smiles, _catalog_id in itertools.islice(_iter_smiles(input_path), sample_size):
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            mols.append(Chem.AddHs(mol))
    if not mols:
        logger.error("no valid molecules parsed from %s for tuning", input_path)
        sys.exit(1)
    return mols


def _run_autotune(
    input_path: Path,
    sample_size: int,
    seed: int,
    output_dir: Path,
) -> None:
    from nvmolkit.autotune import save, tune_embed_molecules, tune_mmff_optimize

    logger.info(
        "Sampling %d molecules from %s for autotuning...", sample_size, input_path.name
    )
    mols = _sample_mols_for_tuning(input_path, sample_size, seed)
    logger.info("Sampled %d valid molecules.", len(mols))

    embed_params = AllChem.ETKDGv3()
    embed_params.randomSeed = seed
    embed_params.useRandomCoords = True

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running tune_embed_molecules...")
    embed_result = tune_embed_molecules(mols, params=embed_params, seed=seed)
    embed_tune_path = output_dir / "embed_tune.json"
    save(embed_result.best_config, str(embed_tune_path))
    logger.info("Saved embed tuning result to %s", embed_tune_path)

    logger.info("Running tune_mmff_optimize...")
    mmff_result = tune_mmff_optimize(mols, seed=seed)
    mmff_tune_path = output_dir / "mmff_tune.json"
    save(mmff_result.best_config, str(mmff_tune_path))
    logger.info("Saved MMFF tuning result to %s", mmff_tune_path)


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
@click.option("--batch-size", default=50, type=int, help="Batch size")
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
    help="Output Parquet file to blob storage.",
)
@click.option("--bucket", default="lynceus", type=str, help="Output bucket name")
@click.option(
    "--skip-if-exists",
    is_flag=True,
    help="Skip processing if the output file already exists.",
)
@click.option(
    "--tune",
    is_flag=True,
    help="Run nvMolKit autotune against a sample of --input and exit.",
)
@click.option(
    "--tune-sample-size",
    default=2000,
    type=int,
    show_default=True,
    help="Number of molecules to sample from --input for autotuning.",
)
@click.option(
    "--tune-output-dir",
    default="./nvmolkit_tune",
    type=click.Path(file_okay=False),
    show_default=True,
    help="Directory to write tuning result JSON files.",
)
@click.option(
    "--embed-hardware-options",
    "embed_hardware_options_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a saved HardwareOptions JSON for embedding (from --tune).",
)
@click.option(
    "--mmff-hardware-options",
    "mmff_hardware_options_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a saved HardwareOptions JSON for MMFF optimization (from --tune).",
)
def preprocess(
    input_path: str,
    output: str,
    num_workers: int,
    seed: int,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
    batch_size: int,
    tune: bool,
    tune_sample_size: int,
    tune_output_dir: str,
    embed_hardware_options_path: str | None,
    mmff_hardware_options_path: str | None,
):
    if tune:
        if num_workers != 1:
            logger.warning("--tune runs single-process against the GPU")
        with _suppress_native_stderr():
            _run_autotune(
                input_path=Path(input_path),
                sample_size=tune_sample_size,
                seed=seed,
                output_dir=Path(tune_output_dir),
            )
        return

    if use_blob_storage:
        blob_settings = get_blob_storage_settings()
        target_path = f"{bucket}/{output.lstrip('/')}"
        filesystem = S3FileSystem(
            access_key=blob_settings.access_key_id,
            secret_key=blob_settings.access_key,
            endpoint_override=blob_settings.endpoint,
            region=blob_settings.region,
            scheme="https" if blob_settings.use_ssl else "http",
        )
    else:
        target_path = output
        filesystem = LocalFileSystem()

    if skip_if_exists:
        file_info = filesystem.get_file_info(target_path)
        if file_info.type != FileType.NotFound:
            logger.info("%s already exists. Skipping.", target_path)
            return

    steps = _build_pipeline(
        seed,
        embed_hardware_options_path=Path(embed_hardware_options_path)
        if embed_hardware_options_path
        else None,
        mmff_hardware_options_path=Path(mmff_hardware_options_path)
        if mmff_hardware_options_path
        else None,
    )

    with _suppress_native_stderr():
        _preprocess(
            input_path=Path(input_path),
            num_workers=num_workers,
            batch_size=batch_size,
            steps=steps,
            target_path=target_path,
            filesystem=filesystem,
        )
