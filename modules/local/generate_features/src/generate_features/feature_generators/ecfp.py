# modules/local/feature_generation/src/feature_generation/feature_generators/ecfp.py

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import ECFPFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class ECFPFeature(FeatureGenerator):
    name = "ecfp"

    DEFAULT_FP_SIZE = 1024
    DEFAULT_ECFP_RADIUS = 3

    def __init__(
        self, fp_size: int = DEFAULT_FP_SIZE, radius: int = DEFAULT_ECFP_RADIUS
    ) -> None:
        self._fp_size = fp_size
        self._fp = ECFPFingerprint(
            fp_size=fp_size, radius=radius, n_jobs=1, sparse=False
        )

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from ECFPFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.uint8(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [0] * self._fp_size
