# projects/lynceus-dock/src/lynceus_dock/common/ligand.py

import typing
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generator

import pyarrow.parquet as pq
from lynceus_core.logging import get_lynceus_logger
from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem

from lynceus_dock.common.types import DockingError, LigandRecord

_ID_COL = "id"
_SDF_COL = "conformer"
_DEFAULT_BATCH_SIZE = 1024

logger = get_lynceus_logger()


class LigandPrepError(DockingError):
    """Raised when Mol bytes fail to deserialize or Meeko prep fails."""


class LigandRecordReadError(DockingError):
    """Raised when the ligand parquet is missing expected columns or
    contains rows that fail to parse as valid RDKit Mols."""


def _mol_from_bytes(mol_bytes: bytes) -> Chem.Mol:
    mol = Chem.Mol(typing.cast(Chem.Mol, mol_bytes))
    if mol is None:
        raise LigandPrepError("Failed to deserialize RDKit Mol from bytes")
    return mol


def write_ligand_pdbqt(ligand: LigandRecord, dest_dir: Path) -> Path:
    mol = _mol_from_bytes(ligand.mol_bytes)

    preparator = MoleculePreparation()
    setups = preparator.prepare(mol)
    if not setups:
        raise LigandPrepError(f"Meeko produced no setups for ligand {ligand.ligand_id}")

    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setups[0])
    if not is_ok:
        raise LigandPrepError(
            f"Meeko PDBQT write failed for {ligand.ligand_id}: {error_msg}"
        )

    out_path = dest_dir / f"{ligand.ligand_id}.pdbqt"
    out_path.write_text(pdbqt_string)
    return out_path


@contextmanager
def materialize_ligands(
    ligands: list[LigandRecord],
) -> Generator[dict[str, Path], None, None]:
    """Write each LigandRecord to a temp PDBQT file. Yields ligand_id -> Path.
    Cleans up the temp directory on context exit."""
    with TemporaryDirectory(prefix="docking_ligands_", delete=False) as tmp:
        tmp_path = Path(tmp)
        paths: dict[str, Path] = {}
        for ligand in ligands:
            paths[ligand.ligand_id] = write_ligand_pdbqt(ligand, tmp_path)
        yield paths


def _open_parquet(
    parquet_path: str | Path, required_cols: tuple[str, ...] = ()
) -> pq.ParquetFile:
    parquet_file = pq.ParquetFile(parquet_path)
    missing = [
        col for col in required_cols if col not in parquet_file.schema_arrow.names
    ]
    if missing:
        raise LigandRecordReadError(
            f"Parquet {parquet_path} is missing expected column(s): {missing}"
        )
    return parquet_file


def count_ligand_rows(parquet_path: str | Path) -> int:
    return _open_parquet(parquet_path).metadata.num_rows


def _mol_from_molblock(molblock: str) -> Chem.Mol:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        raise LigandRecordReadError("Failed to parse conformer_sdf as a valid molblock")
    return mol


def iter_ligand_records(
    parquet_path: str | Path,
    id_col: str = _ID_COL,
    sdf_col: str = _SDF_COL,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> Iterator[LigandRecord]:
    parquet_file = _open_parquet(parquet_path, (id_col, sdf_col))

    n_skipped_empty = 0

    for batch in parquet_file.iter_batches(
        batch_size=batch_size, columns=[id_col, sdf_col]
    ):
        ids = batch.column(id_col).to_pylist()
        molblocks = batch.column(sdf_col).to_pylist()

        for ligand_id, molblock in zip(ids, molblocks, strict=True):
            if not molblock:
                n_skipped_empty += 1
                continue

            mol = _mol_from_molblock(molblock)
            yield LigandRecord(ligand_id=ligand_id, mol_bytes=mol.ToBinary())

    if n_skipped_empty:
        logger.warning(
            "Rows skipped due to empty column",
            n_skipped=n_skipped_empty,
            column=sdf_col,
        )
        logger.warning(
            "%d row(s) skipped due to empty %s.",
            n_skipped_empty,
            sdf_col,
        )
