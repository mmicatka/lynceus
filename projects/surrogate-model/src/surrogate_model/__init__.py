# projects/surrogate-model/src/surrogate_model/__init__.py

from .cli import sample_candidates, sample_candidates_by_prediction, train_model

__all__ = ["sample_candidates", "sample_candidates_by_prediction", "train_model"]
