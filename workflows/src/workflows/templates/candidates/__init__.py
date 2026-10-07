# workflows/src/workflows/templates/candidates/__init__.py

from .load import build_load_candidates_template
from .shard import build_shard_candidates_template

__all__ = ["build_load_candidates_template", "build_shard_candidates_template"]
