# projects/lynceus-dock/src/lynceus_dock/providers/utils.py


import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from lynceus_dock.common.types import (
    DockingError,
    DockingResult,
    LigandRecord,
    SearchBox,
)


class ProviderNotAvailableError(DockingError):
    """Raised by validate_environment() when a provider's runtime deps are missing."""


class DockingProvider(ABC):
    """Common interface for Vina-family docking backends."""

    @abstractmethod
    def validate_environment(self) -> None: ...

    @abstractmethod
    def dock(
        self,
        receptor_path: Path,
        ligand: LigandRecord,
        box: SearchBox,
        scoring_mode: str = "",
    ) -> list[DockingResult]:
        """Dock a single ligand against a single receptor. Returns one
        DockingResult per output pose/mode."""
        ...

    @abstractmethod
    def dock_batch(
        self,
        receptor_path: Path,
        ligands: list[LigandRecord],
        box: SearchBox,
        batch_size: int | None = None,
        scoring_mode: str = "",
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        """Dock each ligand in `ligands` independently against the same
        receptor + search box, yielding results incrementally.

        Args:
            batch_size: max ligands per underlying provider invocation.
                Providers that have no native batch primitive may ignore
                this (falling back to dock() per ligand); providers with
                a native batch primitive should chunk `ligands` into
                groups of at most `batch_size`. `None` means "use the
                provider's default."

        Yields:
            (ligand_id, results) pairs. ligand_id is LigandRecord.ligand_id
            (not a filename stem, since ligands no longer arrive as files).
            Yield granularity is provider-specific
        """
        ...


_RESULT_LINE = re.compile(
    r"^REMARK VINA RESULT:\s*"
    r"(?P<affinity>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_lb>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_ub>-?\d+\.?\d*)",
)


def parse_vina_output_pdbqt(output_pdbqt: Path, ligand_id: str) -> list[DockingResult]:
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
