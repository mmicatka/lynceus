# libs/lynceus-chem/src/lynceus_chem/preprocess/preprocess.py

import argparse
import gzip
import json
import logging
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdFingerprintGenerator
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

from .cns_mpo import cns_mpo_from_mol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500

_pains_catalog: FilterCatalog | None = None
_mfp_gen: Any = None
_morgan_n_bits: int = 0


def _build_arrow_schema(morgan_n_bits: int) -> pa.Schema:
    return pa.schema(
        [
            ("catalog_id", pa.string()),
            ("smiles", pa.string()),
            ("parse_ok", pa.bool_()),
            ("heavy_atom_count", pa.int16()),
            ("molecular_weight", pa.float32()),
            ("morgan_fp", pa.list_(pa.uint8(), morgan_n_bits)),
            ("cns_mpo", pa.float32()),
            ("cns_mpo_components", pa.string()),
            ("pains_flags", pa.list_(pa.string())),
        ]
    )


def _build_pains_catalog():
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_C)

    global _pains_catalog
    _pains_catalog = FilterCatalog(params)


def pains_flags_for(mol: Chem.Mol, catalog: FilterCatalog) -> list[str]:
    matches = catalog.GetMatches(mol)
    return [m.GetDescription() for m in matches]


def _build_fingerprint_gen(
    morgan_radius: int,
    morgan_n_bits: int,
):
    global _mfp_gen
    _mfp_gen = rdFingerprintGenerator.GetMorganGenerator(
        radius=morgan_radius, fpSize=morgan_n_bits
    )


def _preprocess_record(record: tuple[str, str]) -> dict:
    if not _pains_catalog:
        return {}

    smiles, catalog_id = record
    mol = Chem.MolFromSmiles(smiles)

    if mol is None:
        return {
            "catalog_id": catalog_id,
            "smiles": smiles,
            "parse_ok": False,
            "heavy_atom_count": None,
            "molecular_weight": None,
            "morgan_fp": np.zeros(_morgan_n_bits, dtype=np.uint8),
            "cns_mpo": None,
            "cns_mpo_components": {},
            "pains_flags": [],
        }

    morgan_fp = _mfp_gen.GetFingerprintAsNumPy(mol)
    pains_flags = sorted(
        {match.GetDescription().split()[0] for match in _pains_catalog.GetMatches(mol)}
    )

    cns_mpo = cns_mpo_from_mol(mol)

    heavy_atom_count = mol.GetNumHeavyAtoms()
    molecular_weight = Descriptors.MolWt(mol)

    return {
        "catalog_id": catalog_id,
        "smiles": smiles,
        "parse_ok": True,
        "heavy_atom_count": heavy_atom_count,
        "molecular_weight": molecular_weight,
        "morgan_fp": morgan_fp,
        "cns_mpo": cns_mpo["cns_mpo"],
        "cns_mpo_components": {
            "clogp": cns_mpo["clogp"],
            "clogd": cns_mpo["clogd"],
            "mw": cns_mpo["mw"],
            "tpsa": cns_mpo["tpsa"],
            "hbd": cns_mpo["hbd"],
            "pka": cns_mpo["pka"],
            "clogp_d": cns_mpo["clogp_d"],
            "clogd_d": cns_mpo["clogd_d"],
            "mw_d": cns_mpo["mw_d"],
            "tpsa_d": cns_mpo["tpsa_d"],
            "hbd_d": cns_mpo["hbd_d"],
            "pka_d": cns_mpo["pka_d"],
        },
        "pains_flags": pains_flags,
    }


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


def _results_to_frame(results: list[dict], morgan_n_bits: int) -> pl.DataFrame:
    morgan_stack = np.stack(
        [r["morgan_fp"] for r in results]
    )  # (n, morgan_n_bits) uint8

    return pl.DataFrame(
        {
            "catalog_id": [r["catalog_id"] for r in results],
            "smiles": [r["smiles"] for r in results],
            "parse_ok": [r["parse_ok"] for r in results],
            "heavy_atom_count": [r["heavy_atom_count"] for r in results],
            "molecular_weight": [r["molecular_weight"] for r in results],
            "morgan_fp": morgan_stack,
            "cns_mpo": [r["cns_mpo"] for r in results],
            "cns_mpo_components": [
                json.dumps(r["cns_mpo_components"]) for r in results
            ],
            "pains_flags": [r["pains_flags"] for r in results],
        },
        schema={
            "catalog_id": pl.String,
            "smiles": pl.String,
            "parse_ok": pl.Boolean,
            "heavy_atom_count": pl.Int16,
            "molecular_weight": pl.Float32,
            "morgan_fp": pl.Array(pl.UInt8, morgan_n_bits),
            "cns_mpo": pl.Float32,
            "cns_mpo_components": pl.String,
            "pains_flags": pl.List(pl.String),
        },
    )


def _init_worker(morgan_radius: int, morgan_n_bits: int) -> None:
    """Initializes global variables inside each pool worker process."""
    global _morgan_n_bits
    _morgan_n_bits = morgan_n_bits
    _build_pains_catalog()
    _build_fingerprint_gen(morgan_radius, morgan_n_bits)


def _preprocess(
    input_path: Path,
    output_path: Path,
    morgan_radius: int,
    morgan_n_bits: int,
    num_workers: int,
) -> None:
    logger.info("starting preprocessing with %d workers", num_workers)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = _build_arrow_schema(morgan_n_bits)

    n_written = 0
    n_failed = 0

    log_interval = 50_000  # Log every 50k records
    next_log_threshold = log_interval

    writer = None

    try:
        with Pool(
            processes=num_workers,
            initializer=_init_worker,
            initargs=(morgan_radius, morgan_n_bits),
        ) as pool:
            for chunk_results in _batch(
                pool.imap(
                    _preprocess_record, _iter_smiles(input_path), chunksize=_CHUNK_SIZE
                ),
                _CHUNK_SIZE,
            ):
                n_failed += sum(1 for r in chunk_results if not r["parse_ok"])
                frame = _results_to_frame(chunk_results, morgan_n_bits)
                arrow_table = frame.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(output_path, schema, compression="zstd")
                writer.write_table(arrow_table.cast(schema))
                n_written += len(chunk_results)

                if n_written >= next_log_threshold:
                    logger.info(
                        "Progress: processed %d records (failed parse: %d)",
                        n_written,
                        n_failed,
                    )
                    next_log_threshold += log_interval
    finally:
        if writer is not None:
            writer.close()

    if n_failed:
        logger.warning("%d records failed to parse", n_failed)
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

    return p.parse_args()


def preprocess():
    args = _parse_args()
    _preprocess(
        input_path=args.input,
        output_path=args.output,
        morgan_radius=args.morgan_radius,
        morgan_n_bits=args.morgan_n_bits,
        num_workers=args.num_workers,
    )
