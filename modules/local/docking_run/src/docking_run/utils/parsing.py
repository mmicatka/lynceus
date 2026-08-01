# modules/local/docking_run/src/docking_run/utils/parsing.py


import re
from pathlib import Path

from docking_run.types import DockingError, DockingResult

_RESULT_LINE = re.compile(
    r"^REMARK VINA RESULT:\s*"
    r"(?P<affinity>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_lb>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_ub>-?\d+\.?\d*)",
)


def parse_vina_output_pdbqt(output_pdbqt: Path, ligand_id: str) -> list[DockingResult]:
    """Parse a Vina-style multi-MODEL output PDBQT into DockingResults.

    Each MODEL/ENDMDL block becomes one DockingResult with mode = the
    1-indexed model number. Individual pose coordinates are left on disk
    (referenced via pose_pdbqt) rather than materialized in memory, since
    downstream consumers (e.g. complex generation) read them directly.
    """
    if not output_pdbqt.is_file():
        raise DockingError(f"Expected output PDBQT not found: {output_pdbqt}")

    text = output_pdbqt.read_text()
    results: list[DockingResult] = []
    mode = 0
    for line in text.splitlines():
        if line.startswith("MODEL"):
            mode += 1
        match = _RESULT_LINE.match(line)
        if match:
            results.append(
                DockingResult(
                    ligand_id=ligand_id,
                    pose_pdbqt=output_pdbqt,
                    affinity_kcal_mol=float(match["affinity"]),
                    mode=mode if mode > 0 else 1,
                    rmsd_lb=float(match["rmsd_lb"]),
                    rmsd_ub=float(match["rmsd_ub"]),
                )
            )

    if not results:
        raise DockingError(
            f"No REMARK VINA RESULT lines found in {output_pdbqt}; "
            "docking may have failed silently."
        )
    return results
