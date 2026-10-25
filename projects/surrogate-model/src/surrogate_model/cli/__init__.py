# projects/surrogate-model/src/surrogate_model/cli/__init__.py

from .sample import sample_surrogate_candidates
from .sample_by_prediction import sample_candidates_by_prediction
from .train import train_model

__all__ = [
    "sample_surrogate_candidates",
    "sample_candidates_by_prediction",
    "train_model",
]
