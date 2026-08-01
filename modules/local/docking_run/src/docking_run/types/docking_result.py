# modules/local/docking_run/src/docking_run/types/docking_result.py

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DockingResult:
    ligand_id: str
    pose_pdbqt: Path
    affinity_kcal_mol: float
    mode: int
    rmsd_lb: float | None = None
    rmsd_ub: float | None = None
