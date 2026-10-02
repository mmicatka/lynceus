# modules/local/generate_features/src/generate_features/feature_generators/descriptors.py # noqa: E501

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import RDKit2DDescriptorsFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class DescriptorsFeature(FeatureGenerator):
    name = "descriptors"

    def __init__(self) -> None:
        self._fp = RDKit2DDescriptorsFingerprint(n_jobs=1, sparse=False)
        self._fp_size = self._fp.n_features_out

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from RDKit2DDescriptorsFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [0.0] * self._fp_size
