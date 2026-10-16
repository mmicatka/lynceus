# modules/local/surrogate_model/src/surrogate_model/__init__.py

from .cli import sample_candidates, train_model
from .data import flatten_features, label, load_and_clean_data
from .metrics import evaluation_metrics, predict_active, recall_at_k

__all__ = [
    # data
    "flatten_features",
    "label",
    "load_and_clean_data",
    # metrics
    "predict_active",
    "evaluation_metrics",
    "recall_at_k",
    # sample
    "sample_candidates",
    # model
    "train_model",
]
