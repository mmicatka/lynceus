# projects/surrogate-model/src/surrogate_model/__init__.py

from .cli import (
    plan_surrogate_sample,
    sample_candidates,
    train_model,
)

__all__ = [
    "plan_surrogate_sample",
    "sample_candidates",
    "train_model",
]
