# modules/local/preprocess_candidates/src/preprocess.py

"""
Preprocess a single downloaded candidate file (.smi.gz, tab-separated
SMILES + catalog ID — e.g. ZINC's format) into a Parquet file of
per-molecule descriptors.

Columns written:
    id                    InChIKey of the canonical (parent) molecule
    canonical_smiles      RDKit canonical SMILES
    catalog_id            source catalog identifier (e.g. ZincId), as given in the input
    cns_mpo_score         composite 0-6 CNS-MPO score (Wager et al. 2010)
    cns_mpo_components    struct of the 6 underlying properties and their
                           individual 0-1 desirability scores (clogp, clogd,
                           mw, tpsa, hbd, pka + *_d desirability for each)
    heavy_atom_count      integer heavy (non-H) atom count
    molecular_weight      float, RDKit-computed
    pains_flags           list[str] of matched PAINS alert names (empty if none)
"""

from __future__ import annotations

import argparse
import gzip
import logging
import sys
from pathlib import Path
import time

import polars as pl
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from src.cns_mpo import cns_mpo_from_mol


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")


def build_pains_catalog() -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    return FilterCatalog(params)


def pains_flags_for(mol: Chem.Mol, catalog: FilterCatalog) -> list[str]:
    matches = catalog.GetMatches(mol)
    return [m.GetDescription() for m in matches]


def iter_smi_gz(path: Path):
    """
    Yield (smiles, catalog_id) tuples from a gzipped, tab-separated
    (SMILES, catalog_id) file. Blank lines are skipped. A header row
    is tolerated and skipped if the first field doesn't parse as SMILES.
    """
    with gzip.open(path, "rt") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                logger.warning(
                    "Line %d: expected 2 tab-separated fields, got %d — skipping",
                    line_num,
                    len(parts),
                )
                continue
            smiles, catalog_id = parts[0], parts[1]
            yield line_num, smiles, catalog_id


def process_file(input_path: Path, output_path: Path, log_every: int = 1000) -> None:
    pains_catalog = build_pains_catalog()

    records = []
    n_seen = 0
    n_failed = 0

    start_time = time.now()

    for line_num, smiles, catalog_id in iter_smi_gz(input_path):
        n_seen += 1

        if n_seen % log_every == 0:
            elapsed = time.time() - start_time
            records_per_sec = n_seen / elapsed if elapsed > 0 else 0
            logger.info(
                "%s: processed %d records in %.2f seconds (%.2f rec/sec), %d failed/skipped",
                input_path,
                n_seen,
                elapsed,
                records_per_sec,
                n_failed,
            )

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning(
                "Line %d: could not parse SMILES %r (catalog_id=%s) — skipping",
                line_num,
                smiles,
                catalog_id,
            )
            n_failed += 1
            continue

        canonical_smiles = Chem.MolToSmiles(mol, canonical=True)
        inchikey = Chem.MolToInchiKey(mol)

        if not inchikey:
            logger.warning(
                "Line %d: RDKit could not compute an InChIKey for %r (catalog_id=%s) — skipping",
                line_num,
                smiles,
                catalog_id,
            )
            n_failed += 1
            continue

        cns_mpo = cns_mpo_from_mol(mol)

        records.append(
            {
                "id": inchikey,
                "canonical_smiles": canonical_smiles,
                "catalog_id": catalog_id,
                "cns_mpo_score": cns_mpo["cns_mpo"],
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
                "heavy_atom_count": mol.GetNumHeavyAtoms(),
                "molecular_weight": Descriptors.MolWt(mol),
                "pains_flags": pains_flags_for(mol, pains_catalog),
            }
        )

    if not records:
        sys.exit(f"ERROR: no valid molecules parsed from {input_path}")

    df = pl.from_dicts(records)
    df.write_parquet(output_path)

    logger.info(
        "Processed %s: %d records seen, %d failed/skipped, %d written -> %s",
        input_path,
        n_seen,
        n_failed,
        len(df),
        output_path,
    )


def parse_args():
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
    return p.parse_args()


def main():
    args = parse_args()
    process_file(args.input, args.output)


if __name__ == "__main__":
    main()
