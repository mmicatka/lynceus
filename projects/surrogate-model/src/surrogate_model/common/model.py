# projects/surrogate-model/src/surrogate_model/common/model.py


from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol

import lightgbm as lgb
import numpy as np
import scipy.sparse as sp
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

type MatrixLike = np.ndarray | sp.spmatrix
type LGBMOutput = MatrixLike | list[sp.spmatrix]


class ProbabilisticClassifier[T](Protocol):
    def predict(self, X: Any, *args: Any, **kwargs: Any) -> T: ...
    def predict_proba(self, X: Any, *args: Any, **kwargs: Any) -> T: ...


class TrainableClassifier[T](ProbabilisticClassifier[T], Protocol):
    def fit(self, X: Any, y: Any, *args: Any, **kwargs: Any) -> Any: ...


class ModelType(StrEnum):
    LIGHTGBM = "lightgbm"
    MLP = "mlp"


DEFAULT_MODEL_TYPE = ModelType.LIGHTGBM

type ModelBuilder = Callable[[int], TrainableClassifier[Any]]

_MODEL_REGISTRY: dict[ModelType, ModelBuilder] = {}


def register_model(model_type: ModelType) -> Callable[[ModelBuilder], ModelBuilder]:
    def decorator(builder: ModelBuilder) -> ModelBuilder:
        _MODEL_REGISTRY[model_type] = builder
        return builder

    return decorator


def build_model(model_type: ModelType, random_state: int) -> TrainableClassifier[Any]:
    try:
        builder = _MODEL_REGISTRY[model_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported model type: {model_type}") from exc
    return builder(random_state)


@register_model(ModelType.LIGHTGBM)
def _build_lightgbm(random_state: int) -> TrainableClassifier[Any]:
    return lgb.LGBMClassifier(
        objective="binary",
        n_estimators=100,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=10,
        random_state=random_state,
        deterministic=True,
        force_row_wise=True,
    )


@register_model(ModelType.MLP)
def _build_mlp(random_state: int) -> TrainableClassifier[Any]:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                MLPClassifier(
                    hidden_layer_sizes=(128, 64),
                    activation="relu",
                    learning_rate_init=1e-3,
                    max_iter=200,
                    early_stopping=True,
                    random_state=random_state,
                ),
            ),
        ]
    )
