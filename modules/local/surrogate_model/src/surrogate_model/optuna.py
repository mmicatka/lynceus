# modules/local/surrogate_model/src/surrogate_model/optuna.py

import lightgbm as lgb
import numpy as np
import optuna
from skfp.metrics import bedroc_score, enrichment_factor
from sklearn.model_selection import KFold


def make_objective(
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    primary_metric: str = "bedroc",
    active_quantile: float = 0.05,
    random_seed: int = 1000,
):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "regression",
            "metric": "rmse",
            "verbosity": -1,
            "boosting_type": "gbdt",
            "deterministic": True,
            "force_row_wise": True,
            "random_state": random_seed,
            "num_leaves": trial.suggest_int("num_leaves", 16, 128),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 5e-3, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 800),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }

        kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_seed)
        fold_metrics: list[dict[str, float]] = []

        for train_idx, val_idx in kf.split(X):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = lgb.LGBMRegressor(**params)
            model.fit(
                X_train,
                y_train,
                eval_X=X_val,
                eval_y=y_val,
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )

            y_pred = np.asarray(model.predict(X_val))

            # Define active ground truth (lower/more negative kcal/mol is better)
            affinity_threshold = np.quantile(y_val, active_quantile)
            y_true_binary = (y_val <= affinity_threshold).astype(int)

            # Invert predicted affinities so higher score = better predicted binder
            scores = -y_pred

            metrics = {
                "ef_top_1_percent": float(
                    enrichment_factor(y_true_binary, scores, fraction=0.01)
                ),
                "ef_top_5_percent": float(
                    enrichment_factor(y_true_binary, scores, fraction=0.05)
                ),
                "bedroc": float(bedroc_score(y_true_binary, scores, alpha=20.0)),
            }
            fold_metrics.append(metrics)

        agg = {
            key: float(np.mean([fm[key] for fm in fold_metrics]))
            for key in fold_metrics[0]
        }
        for key, value in agg.items():
            trial.set_user_attr(key, value)

        return agg[primary_metric]

    return objective
