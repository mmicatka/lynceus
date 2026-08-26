# modules/local/docking_run/src/docking_run/prep/ligand_prep.py

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generator

from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem

from docking_run.types import DockingError, LigandRecord


class LigandPrepError(DockingError):
    """Raised when Mol bytes fail to deserialize or Meeko prep fails."""


def _mol_from_bytes(mol_bytes: bytes) -> Chem.Mol:
    mol = Chem.Mol(mol_bytes)
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
def materialize_ligands(ligands: list[LigandRecord]) -> Generator[dict[str, Path]]:
    """Write each LigandRecord to a temp PDBQT file. Yields ligand_id -> Path.
    Cleans up the temp directory on context exit."""
    with TemporaryDirectory(prefix="docking_ligands_") as tmp:
        tmp_path = Path(tmp)
        paths: dict[str, Path] = {}
        for ligand in ligands:
            paths[ligand.ligand_id] = write_ligand_pdbqt(ligand, tmp_path)
        yield paths
