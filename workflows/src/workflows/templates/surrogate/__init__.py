# workflows/src/workflows/template/surrogate/__init__.py


from .sample import (
    surrogate_sample_by_prediction_template,
    surrogate_sample_template,
)
from .train import surrogate_train_template

__all__ = [
    "surrogate_sample_template",
    "surrogate_sample_by_prediction_template",
    "surrogate_train_template",
]
