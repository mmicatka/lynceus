# modules/local/docking_run/src/docking_run/providers/abstract_provider.py

from abc import ABC, abstractmethod
from pathlib import Path


class DockingProvider(ABC):
    """Abstract base class for all molecular docking engines."""

    @abstractmethod
    def dock(self, receptor: Path, ligand: Path, output: Path, **kwargs) -> bool:
        """
        Execute the docking simulation.
        Must be implemented by all subclasses.
        """
        pass

    @abstractmethod
    def check_installed(self) -> bool:
        """Verify the underlying binary is available on the system."""
        pass
