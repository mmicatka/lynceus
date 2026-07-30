# modules/local/docking_prep/src/docking_prep/ligand/conformer_generate.py

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import dimorphite_dl
import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

warnings.filterwarnings("ignore", category=SyntaxWarning, module="prody")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _select_protonation_state(
    smiles: str,
    ph_min: float = 6.4,
    ph_max: float = 8.4,
) -> str:
    variants = dimorphite_dl.protonate_smiles(
        smiles, ph_min=ph_min, ph_max=ph_max, validate_output=True
    )
    if not variants:
        raise ValueError(
            f"Dimorphite-DL returned no protonation states for SMILES: {smiles!r}"
        )

    def sort_key(variant_smiles: str) -> tuple[int, str]:
        mol = Chem.MolFromSmiles(variant_smiles)
        if mol is None:
            return (10**6, variant_smiles)
        formal_charge = Chem.GetFormalCharge(mol)
        canonical = Chem.MolToSmiles(mol)
        return (abs(formal_charge), canonical)

    return min(variants, key=sort_key)


def _embed_and_minimize(smiles: str, random_seed: int = 42) -> tuple[bytes | None, str]:
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return None, "SMILES_PARSE_FAILED"

    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed

    if AllChem.EmbedMolecule(mol, params) != 0:
        return None, "EMBEDDING_FAILED"

    try:
        if AllChem.MMFFOptimizeMolecule(mol) == -1:
            return None, "MINIMIZATION_FAILED"
    except Exception as exc:
        return None, f"MINIMIZATION_EXCEPTION: {exc}"

    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    writer.write(mol)
    writer.flush()
    return buf.getvalue().encode(), "SUCCESS"


def _process_ligand(
    row: dict, ph_min: float, ph_max: float, random_seed: int
) -> tuple[dict, bytes | None, str | None]:
    """Worker function for multiprocessing."""
    # Attempt to gracefully find the correct columns if casing/naming varies slightly
    cat_key = next(
        (k for k in row.keys() if k.lower() in ("catalog_id", "candidate_id", "id")),
        "catalog_id",
    )
    smi_key = next((k for k in row.keys() if k.lower() == "smiles"), "smiles")

    catalog_id = row.get(cat_key)
    smiles = row.get(smi_key)

    sdf_bytes = None
    error = "SUCCESS"

    if not smiles:
        error = "NO_SMILES"
    else:
        try:
            prot_smiles = _select_protonation_state(
                smiles, ph_min=ph_min, ph_max=ph_max
            )
            sdf_bytes, error = _embed_and_minimize(prot_smiles, random_seed=random_seed)
        except Exception as exc:
            error = f"EXCEPTION: {exc}"

    # Update row dict for the new parquet file
    row["error"] = error
    return row, sdf_bytes, catalog_id


def _conformer_generate(
    input: Path,
    output_dir: Path,
    ph_min: float,
    ph_max: float,
    random_seed: int,
    num_workers: int,
    batch_size: int,
    num_shards: int,
):
    input_pq = pq.ParquetFile(input)
    schema = input_pq.schema.to_arrow_schema()
    schema = schema.append(pa.field("error", pa.string()))

    # Prepare output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    partitions_dir = output_dir / "partitions"
    for i in range(num_shards):
        (partitions_dir / str(i)).mkdir(parents=True, exist_ok=True)

    # Partial function to lock in constants for the worker
    worker_func = partial(
        _process_ligand, ph_min=ph_min, ph_max=ph_max, random_seed=random_seed
    )

    logger.info(f"Starting ProcessPoolExecutor with {num_workers} workers.")

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        with pq.ParquetWriter(output_dir / "output.parquet", schema) as writer:
            for batch_idx, batch in enumerate(
                input_pq.iter_batches(batch_size=batch_size)
            ):
                logger.info(f"Processing batch {batch_idx + 1}...")
                processed_records = []

                for row, sdf_bytes, catalog_id in executor.map(
                    worker_func, batch.to_pylist()
                ):
                    if sdf_bytes and catalog_id is not None:
                        try:
                            shard = int(catalog_id) % num_shards
                        except (ValueError, TypeError):
                            shard = zlib.crc32(str(catalog_id).encode()) % num_shards

                        sdf_path = partitions_dir / str(shard) / f"{catalog_id}.sdf"
                        sdf_path.write_bytes(sdf_bytes)

                    processed_records.append(row)

                # Write the updated rows to output.parquet
                out_batch = pa.RecordBatch.from_pylist(processed_records, schema=schema)
                writer.write_batch(out_batch)

    logger.info("Generation complete.")


def _parse_num_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Generate ranked, deduplicated multi-conformer PDBQT sets per "
            "candidate from a Parquet file of SMILES, packaged as an LMDB "
            "keyed by candidate id."
        )
    )
    p.add_argument("--input", required=True, type=Path, help="Input Parquet file.")
    p.add_argument("--output-dir", required=True, type=Path, help="Output directory.")
    p.add_argument(
        "--ph-min",
        type=float,
        default=6.4,
        help="Minimum pH (default: 6.4).",
    )
    p.add_argument(
        "--ph-max",
        type=float,
        default=8.4,
        help="Maximum pH (default: 8.4).",
    )
    p.add_argument(
        "--random-seed",
        type=int,
        default=1000,
        help="ETKDG random seed (default: 1000).",
    )
    p.add_argument(
        "--num-workers", metavar="N|auto", default="auto", type=_parse_num_workers
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    p.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size (default: 1000).",
    )
    p.add_argument("--num_shards", type=int, default=10, help="Number of shards.")
    return p.parse_args()


def conformer_generate():
    args = _parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    _conformer_generate(
        input=args.input,
        output_dir=args.output_dir,
        ph_min=args.ph_min,
        ph_max=args.ph_max,
        random_seed=args.random_seed,
        num_workers=args.num_workers,
        batch_size=args.batch_size,
        num_shards=args.num_shards,
    )
