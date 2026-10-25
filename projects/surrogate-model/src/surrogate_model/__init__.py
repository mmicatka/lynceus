# projects/surrogate-model/src/surrogate_model/__init__.py

from .cli import (
    sample_candidates_by_prediction,
    sample_surrogate_candidates,
    train_model,
)

__all__ = [
    "sample_surrogate_candidates",
    "sample_candidates_by_prediction",
    "train_model",
]
