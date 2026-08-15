# modules/local/surrogate_model/src/surrogate_model/metrics.py

import numpy as np
from scipy.stats import spearmanr


def enrichment_factor(
    y_true: np.ndarray, y_pred: np.ndarray, top_frac: float = 0.01
) -> float:
    n = len(y_true)
    k = max(1, int(np.ceil(n * top_frac)))

    true_top_idx = set(np.argsort(y_true)[:k])
    pred_top_idx = set(np.argsort(y_pred)[:k])

    hits = len(true_top_idx & pred_top_idx)
    return (hits / k) / top_frac


def top_k_recall(
    y_true: np.ndarray, y_pred: np.ndarray, top_frac: float = 0.01
) -> float:
    n = len(y_true)
    k = max(1, int(np.ceil(n * top_frac)))

    true_top_idx = set(np.argsort(y_true)[:k])
    pred_top_idx = set(np.argsort(y_pred)[:k])

    return len(true_top_idx & pred_top_idx) / k


def spearman_corr(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    corr, _ = spearmanr(y_true, y_pred)
    return corr


def surrogate_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, top_fracs: tuple[float, ...] = (0.01, 0.05)
) -> dict[str, float]:
    metrics = {
        "rmse": float(np.sqrt(np.mean((y_true - y_pred) ** 2))),
        "mae": float(np.mean(np.abs(y_true - y_pred))),
        "spearman": float(spearman_corr(y_true, y_pred)),
    }
    for frac in top_fracs:
        pct = int(frac * 100)
        metrics[f"ef_top_{pct}_percent"] = enrichment_factor(y_true, y_pred, frac)
        metrics[f"recall_top_{pct}_percent"] = top_k_recall(y_true, y_pred, frac)
    return metrics
