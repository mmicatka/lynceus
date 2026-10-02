# modules/local/surrogate_model/src/surrogate_model/model/__init__.py

from typing import Any, Protocol

import numpy as np
import scipy.sparse as sp

type MatrixLike = np.ndarray | sp.spmatrix
type LGBMOutput = MatrixLike | list[sp.spmatrix]


class ProbabilisticClassifier[T](Protocol):
    def predict(self, X: Any, *args: Any, **kwargs: Any) -> T: ...
    def predict_proba(self, X: Any, *args: Any, **kwargs: Any) -> T: ...
