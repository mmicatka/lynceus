# modules/local/docking_prep/src/docking_prep/__init__.py

from .ensemble import prepare_ensemble
from .ensemble.models import (
    EnsembleMemberPrepResult,
    EnsemblePrepParams,
    EnsemblePrepResults,
)

__all__ = [
    "prepare_ensemble",
    "EnsemblePrepParams",
    "EnsembleMemberPrepResult",
    "EnsemblePrepResults",
]

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("docking-prep")
except PackageNotFoundError:
    __version__ = "unknown"
