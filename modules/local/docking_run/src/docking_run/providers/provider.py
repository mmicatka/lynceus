# modules/local/docking_run/src/docking_run/providers/provider.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from docking_run.types import DockingError, DockingResult, LigandRecord, SearchBox


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
            Yield granularity is provider-specific — see prior docstring
            notes on batch-primitive providers surfacing multiple pairs
            together, and on failed ligands being silently omitted.
        """
        ...
