# modules/local/surrogate_model/src/surrogate_model/metrics.py

import numpy as np
import polars as pl

from surrogate_model.model import ProbabilisticClassifier


def recall_at_k(y_true, y_score, k) -> float:
    top = np.argsort(y_score)[::-1][:k]
    n_true_positives_in_top_k = y_true[top].sum()
    n_true_positives_total = y_true.sum()
    return n_true_positives_in_top_k / n_true_positives_total


def predict_active(model: ProbabilisticClassifier, x) -> np.ndarray:
    p_all_classes = np.asarray(model.predict_proba(x))
    return p_all_classes[:, 1]


def evaluation_metrics(
    y_true, y_prob, percents: list[float] = [0.01, 0.05, 0.10, 0.15]
):
    sorted_indices = np.argsort(y_prob)[::-1]
    total_actives = int(y_true.sum())

    results = []

    for pct in percents:
        k = max(1, int(len(y_true) * pct))
        top = sorted_indices[:k]

        prec = y_true[top].mean()
        rec = y_true[top].sum() / total_actives
        n_caught = int(y_true[top].sum())

        results.append(
            {
                "Top %": pct * 100,
                "Precision": prec,
                "Recall": rec,
                "Num active caught": n_caught,
                "Num active": total_actives,
            }
        )

    return pl.DataFrame(results)
