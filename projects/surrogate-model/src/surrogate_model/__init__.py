# projects/surrogate-model/src/surrogate_model/__init__.py

from .cli import (
    prepare_validation,
    sample_candidates,
    sample_candidates_by_prediction,
    train_model,
)

__all__ = [
    "prepare_validation",
    "sample_candidates",
    "sample_candidates_by_prediction",
    "train_model",
]
