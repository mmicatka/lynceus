# workflows/src/workflows/registry/candidates/__init__.py

from .core import build_candidates_workflow
from .load import build_load_candidates_workflow

__all__ = ["build_candidates_workflow", "build_load_candidates_workflow"]
