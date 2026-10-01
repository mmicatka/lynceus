# modules/local/surrogate_model/src/surrogate_model/__init__.py

from .cli_train import train_model
from .data import flatten_features, label, load_and_clean_data
from .metrics import evaluation_metrics, predict_active, recall_at_k
from .sample_candidates import sample_candidates

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
