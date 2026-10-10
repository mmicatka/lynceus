# workflows/src/workflows/register/candidates/__init__.py

from .load import build_load_candidates_workflow
from .preprocess import build_preprocess_candidates_workflow

__all__ = ["build_load_candidates_workflow", "build_preprocess_candidates_workflow"]
