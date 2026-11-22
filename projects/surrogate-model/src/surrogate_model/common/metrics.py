# projects/surrogate-model/src/surrogate_model/common/metrics.py


from collections.abc import Sequence

import numpy as np
import polars as pl

from surrogate_model.common.model import ProbabilisticClassifier

DEFAULT_EVAL_PERCENTS: tuple[float, ...] = (0.01, 0.05, 0.10, 0.25)


def predict_active(model: ProbabilisticClassifier, x) -> np.ndarray:
    p_all_classes = np.asarray(model.predict_proba(x))
    return p_all_classes[:, 1]


def evaluation_metrics(
    y_true,
    y_prob,
    percents: Sequence[float] = DEFAULT_EVAL_PERCENTS,
) -> pl.DataFrame:
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
