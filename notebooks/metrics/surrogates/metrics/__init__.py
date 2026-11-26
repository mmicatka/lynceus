# notebooks/metrics/surrogates/metrics/__init__.py


from .data import discover_models, load_validation
from .plots import plot_gain_curves, plot_metric_groups, plot_metric_trends
from .score import build_metrics, compute_gain_curves, compute_metrics, score_rounds

__all__ = [
    # data
    "discover_models",
    "load_validation",
    # scores
    "build_metrics",
    "compute_metrics",
    "compute_gain_curves",
    "score_rounds",
    # plots
    "plot_gain_curves",
    "plot_metric_groups",
    "plot_metric_trends",
]
