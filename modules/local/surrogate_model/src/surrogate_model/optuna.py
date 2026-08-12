# modules/local/surrogate_model/src/surrogate_model/optuna.py

import lightgbm as lgb
import numpy as np
import optuna
from sklearn.model_selection import KFold

from surrogate_model.metrics import surrogate_metrics

RECALL_TOP_1 = "recall_top1"


def make_objective(
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    primary_metric: str = RECALL_TOP_1,
    random_seed=1000,
):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "regression",
            "metric": "rmse",
            "verbosity": -1,
            "boosting_type": "gbdt",
            "num_leaves": trial.suggest_int("num_leaves", 16, 256),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 2000),
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

            y_pred = model.predict(X_val)
            fold_metrics.append(surrogate_metrics(y_val, y_pred))

        agg = {
            key: float(np.mean([fm[key] for fm in fold_metrics]))
            for key in fold_metrics[0]
        }
        for key, value in agg.items():
            trial.set_user_attr(key, value)

        return agg[primary_metric]

    return objective
