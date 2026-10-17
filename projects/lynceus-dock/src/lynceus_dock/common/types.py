# projects/lynceus-dock/src/lynceus_dock/common/types.py

from dataclasses import dataclass
from pathlib import Path


class DockingError(RuntimeError):
    """Raised when a provider fails to dock (subprocess failure, bad output, etc.)."""


@dataclass(frozen=True, slots=True)
class DockingResult:
    ligand_id: str
    pose_pdbqt: Path
    affinity_kcal_mol: float
    mode: int
    rmsd_lb: float | None = None
    rmsd_ub: float | None = None


@dataclass(frozen=True)
class LigandRecord:
    ligand_id: str
    mol_bytes: bytes  # RDKit Mol serialized (e.g. Mol.ToBinary())


@dataclass(frozen=True, slots=True)
class SearchBox:
    center: tuple[float, float, float]
    size: tuple[float, float, float]
