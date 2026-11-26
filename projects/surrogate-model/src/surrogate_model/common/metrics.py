# projects/surrogate-model/src/surrogate_model/common/metrics.py


from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import polars as pl

from surrogate_model.common.model import ProbabilisticClassifier

DEFAULT_EVAL_PERCENTS: tuple[float, ...] = (0.01, 0.05, 0.10, 0.25)
DEFAULT_BEDROC_WEIGHT: float = 0.80


def predict_active(model: ProbabilisticClassifier, x) -> np.ndarray:
    p_all_classes = np.asarray(model.predict_proba(x))
    return p_all_classes[:, 1]


def alpha_from_cutoff(
    cutoff_fraction: float,
    weight: float = DEFAULT_BEDROC_WEIGHT,
) -> float:
    if not (0.0 < cutoff_fraction < 1.0):
        raise ValueError(f"cutoff_fraction must be in (0, 1), got {cutoff_fraction}")
    if not (0.0 < weight < 1.0):
        raise ValueError(f"weight must be in (0, 1), got {weight}")
    return float(-np.log1p(-weight) / cutoff_fraction)


BEDROC_ALPHA_TOP_2_PCT: float = alpha_from_cutoff(0.02)  # ~80.5 (80% weight in top 2%)
BEDROC_ALPHA_TOP_1_PCT: float = alpha_from_cutoff(0.01)  # ~160.9 (80% weight in top 1%)
DEFAULT_BEDROC_ALPHAS: tuple[float, ...] = (
    BEDROC_ALPHA_TOP_2_PCT,
    BEDROC_ALPHA_TOP_1_PCT,
)


def _bedroc_from_active_ranks(
    active_ranks: npt.NDArray[np.intp],
    n_samples: int,
    alpha: float,
) -> float:
    n_actives = len(active_ranks)
    if n_actives == 0 or n_actives >= n_samples:
        return float("nan")

    active_ratio = n_actives / n_samples
    norm_ranks = active_ranks / n_samples

    exp_sum = float(np.exp(-alpha * norm_ranks).sum())
    expm1_alpha_n = float(np.expm1(alpha / n_samples))
    expm1_neg_alpha_ra = float(np.expm1(-alpha * active_ratio))
    expm1_neg_alpha_1m_ra = float(np.expm1(-alpha * (1.0 - active_ratio)))

    denom = expm1_neg_alpha_ra * expm1_neg_alpha_1m_ra
    if denom == 0.0:
        return float("nan")

    return (exp_sum * expm1_alpha_n) / denom + 1.0 + (1.0 / expm1_neg_alpha_1m_ra)


def bedroc_score(
    y_true: npt.ArrayLike,
    y_prob: npt.ArrayLike,
    alpha: float = BEDROC_ALPHA_TOP_1_PCT,
) -> float:
    y_true_arr = np.asarray(y_true, dtype=bool)
    y_prob_arr = np.asarray(y_prob)

    sorted_indices = np.argsort(y_prob_arr)[::-1]
    active_ranks = np.flatnonzero(y_true_arr[sorted_indices]) + 1
    return _bedroc_from_active_ranks(active_ranks, len(y_true_arr), alpha)


def evaluation_metrics(
    y_true: npt.ArrayLike,
    y_prob: npt.ArrayLike,
    percents: Sequence[float] = DEFAULT_EVAL_PERCENTS,
    bedroc_alphas: Sequence[float] = DEFAULT_BEDROC_ALPHAS,
) -> pl.DataFrame:
    y_true_arr = np.asarray(y_true, dtype=bool)
    y_prob_arr = np.asarray(y_prob)

    n_samples = len(y_true_arr)
    sorted_indices = np.argsort(y_prob_arr)[::-1]
    active_ranks = np.flatnonzero(y_true_arr[sorted_indices]) + 1
    total_actives = len(active_ranks)
    base_rate = total_actives / n_samples if n_samples > 0 else 0.0

    bedroc_cols = {
        f"BEDROC ({alpha:.1f})": _bedroc_from_active_ranks(
            active_ranks, n_samples, alpha
        )
        for alpha in bedroc_alphas
    }

    results = []
    for pct in percents:
        k = max(1, int(n_samples * pct))
        n_caught = int(np.searchsorted(active_ranks, k, side="right"))

        rec = n_caught / total_actives if total_actives > 0 else float("nan")
        ef = (n_caught / k) / base_rate if base_rate > 0.0 else float("nan")

        results.append(
            {
                "Top %": pct * 100,
                **bedroc_cols,
                "EF": ef,
                "Recall": rec,
                "Num active caught": n_caught,
                "Num active": total_actives,
            }
        )

    return pl.DataFrame(results)
