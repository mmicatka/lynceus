# modules/local/docking_run/src/docking_run/providers/provider.py


from abc import ABC, abstractmethod
from pathlib import Path

from docking_run.types import DockingError, DockingResult, SearchBox


class ProviderNotAvailableError(DockingError):
    """Raised by validate_environment() when a provider's runtime deps are missing."""


class DockingProvider(ABC):
    """Common interface for Vina-family docking backends."""

    @abstractmethod
    def validate_environment(self) -> None:
        """Raise ProviderNotAvailableError if this backend's runtime deps
        (binary on PATH, GPU/driver, etc.) aren't available.

        Callers should invoke this once before dock_batch() so failures
        surface before any (potentially expensive) prep work runs.
        """
        ...

    @abstractmethod
    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: SearchBox,
    ) -> list[DockingResult]:
        """Dock a single ligand against a single receptor. Returns one
        DockingResult per output pose/mode."""
        ...

    @abstractmethod
    def dock_batch(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
    ) -> dict[str, list[DockingResult]]:
        """Dock each ligand in `ligand_pdbqts` independently against the
        same receptor + search box.

        Args:
            batch_size: max ligands per underlying provider invocation.
                Providers that have no native batch primitive may ignore
                this (falling back to dock() per ligand); providers with
                a native batch primitive should chunk `ligand_pdbqts`
                into groups of at most `batch_size`. `None` means "use
                the provider's default."

        Returns:
            Mapping of ligand_id (stem of the ligand_pdbqt filename) to
            its list of DockingResult, in the same order as the poses
            were reported by the backend.
        """
        ...
