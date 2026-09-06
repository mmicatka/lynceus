# modules/local/docking_run/src/docking_run/io/ligand.py

import logging
from typing import Iterator, Optional

import duckdb
from rdkit import Chem

from docking_run.types import DockingError, LigandRecord

logger = logging.getLogger(__name__)

_ID_COL = "catalog_id"
_SDF_COL = "conformer_sdf"


class LigandRecordReadError(DockingError):
    """Raised when the ligand parquet is missing expected columns or
    contains rows that fail to parse as valid RDKit Mols."""


def count_ligand_rows(
    parquet_path: str,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    connection = conn or duckdb.connect()
    res = connection.sql(
        f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"
    ).fetchone()
    if res is None:
        raise RuntimeError(f"DuckDB query returned no relation for {parquet_path}")
    return res[0]


def _mol_from_molblock(molblock: str) -> Chem.Mol:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        raise LigandRecordReadError("Failed to parse conformer_sdf as a valid molblock")
    return mol


def iter_ligand_records(
    parquet_path: str,
    id_col: str = _ID_COL,
    sdf_col: str = _SDF_COL,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> Iterator[LigandRecord]:
    connection = conn or duckdb.connect()
    rel = connection.sql(
        f"SELECT {id_col}, {sdf_col} FROM read_parquet($path)",
        params={"path": parquet_path},
    )

    n_skipped_empty = 0

    for catalog_id, molblock in rel.fetchall():
        if not molblock:
            n_skipped_empty += 1
            logger.warning(
                "Skipping candidate '%s': empty %s with no error_reason set "
                "-- this indicates a gap in upstream error tagging.",
                catalog_id,
                sdf_col,
            )
            continue

        mol = _mol_from_molblock(molblock)
        yield LigandRecord(ligand_id=catalog_id, mol_bytes=mol.ToBinary())

    if n_skipped_empty:
        raise LigandRecordReadError(
            f"{n_skipped_empty} row(s) skipped due to empty {sdf_col} with no "
            f"error_reason -- refusing to proceed with a partial ligand set. "
            f"See preceding WARNING logs for per-candidate detail."
        )
