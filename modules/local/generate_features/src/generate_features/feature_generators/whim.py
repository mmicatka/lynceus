# modules/local/generate_features/src/generate_features/feature_generators/whim.py

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import WHIMFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class WHIMFeature(FeatureGenerator):
    name = "whim"

    N_FEATURES = 114
    DEFAULT_CLIP_VAL = 1e6

    def __init__(self, clip_val: float = DEFAULT_CLIP_VAL) -> None:
        self._fp = WHIMFingerprint(clip_val=clip_val, n_jobs=1)

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from WHIMFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self.N_FEATURES)

    def placeholder_value(self) -> list[float]:
        return [0.0] * self.N_FEATURES
