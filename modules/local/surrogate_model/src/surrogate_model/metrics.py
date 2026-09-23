# modules/local/surrogate_model/src/surrogate_model/label.py

import numpy as np


def recall_at_k(y_true, y_score, k) -> float:
    top = np.argsort(y_score)[::-1][:k]
    n_true_positives_in_top_k = y_true[top].sum()
    n_true_positives_total = y_true.sum()
    return n_true_positives_in_top_k / n_true_positives_total
