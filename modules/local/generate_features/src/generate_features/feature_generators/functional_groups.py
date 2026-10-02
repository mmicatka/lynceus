# modules/local/generate_features/src/generate_features/feature_generators/functional_groups.py # noqa: E501

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import FunctionalGroupsFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class FunctionalGroupsFeature(FeatureGenerator):
    name = "functional_groups"

    N_FEATURES = 85

    def __init__(self) -> None:
        self._fp = FunctionalGroupsFingerprint(count=True, n_jobs=1, sparse=False)

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from FunctionalGroupsFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.uint8(), self.N_FEATURES)

    def placeholder_value(self) -> list[float]:
        return [0] * self.N_FEATURES
