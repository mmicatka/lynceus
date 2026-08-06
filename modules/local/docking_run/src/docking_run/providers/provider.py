# modules/local/docking_run/src/docking_run/providers/provider.py


from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

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
        receptor_path: Path,
        ligand_path: Path,
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
        ligand_paths: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
        scoring_mode: str = "",
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        """Dock each ligand in `ligand_pdbqts` independently against the
        same receptor + search box, yielding results incrementally.

        Args:
            batch_size: max ligands per underlying provider invocation.
                Providers that have no native batch primitive may ignore
                this (falling back to dock() per ligand); providers with
                a native batch primitive should chunk `ligand_pdbqts`
                into groups of at most `batch_size`. `None` means "use
                the provider's default."

        Yields:
            (ligand_id, results) pairs, where ligand_id is the stem of
            the ligand_pdbqt filename and results is that ligand's list
            of DockingResult (in the same order poses were reported by
            the backend).

            Yield granularity is provider-specific and NOT guaranteed to
            be one pair per ligand: providers with a native batch
            primitive (e.g. a single binary invocation covering
            `batch_size` ligands) may only be able to yield once that
            whole underlying invocation completes, in which case several
            (ligand_id, results) pairs surface together rather than as
            each individual ligand finishes. Callers that need a
            completeness/progress guarantee at per-ligand granularity
            should not assume it holds across all providers.

            Ligands that produce no poses (e.g. a docking failure that a
            provider chooses to swallow rather than raise) are silently
            omitted rather than yielded with an empty list; see each
            provider's dock_batch for its exact failure-handling policy.
        """
        ...
