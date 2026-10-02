# modules/local/generate_features/src/generate_features/feature_generators/autocorr.py

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import AutocorrFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class AutocorrFeature(FeatureGenerator):
    name = "autocorr"

    N_FEATURES_2D = 192
    N_FEATURES_3D = 80

    def __init__(self, use_3d: bool = True) -> None:
        self._n_features = self.N_FEATURES_3D if use_3d else self.N_FEATURES_2D
        self._fp = AutocorrFingerprint(use_3D=use_3d, n_jobs=1)

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from AutocorrFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self._n_features)

    def placeholder_value(self) -> list[float]:
        return [0.0] * self._n_features
