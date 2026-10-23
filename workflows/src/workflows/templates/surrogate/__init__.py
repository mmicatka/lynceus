# workflows/src/workflwows/template/surrogate/__init__.py

from .prepare_validation import surrogate_prepare_validation_template
from .sample_surrogate_model import (
    surrogate_sample_by_prediction_template,
    surrogate_sample_template,
)
from .surrogate_train import surrogate_train_template

__all__ = [
    "surrogate_prepare_validation_template",
    "surrogate_sample_template",
    "surrogate_sample_by_prediction_template",
    "surrogate_train_template",
]
