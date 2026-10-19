# projects/surrogate-model/src/surrogate_model/cli/__init__.py

from .sample import sample_candidates
from .train import train_model

__all__ = ["sample_candidates", "train_model"]
