# modules/local/feature_generation/src/feature_generation/feature_generators/morse.py

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import MORSEFingerprint

from feature_generation.feature_generators.feature_generator import FeatureGenerator


class MORSEFeature(FeatureGenerator):
    name = "morse"

    N_FEATURES = 224

    def __init__(self) -> None:
        self._fp = MORSEFingerprint(n_jobs=1)

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from MORSEFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self.N_FEATURES)

    def placeholder_value(self) -> list[float]:
        return [0.0] * self.N_FEATURES
