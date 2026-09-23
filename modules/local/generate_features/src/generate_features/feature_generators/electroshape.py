# modules/local/feature_generation/src/feature_generation/feature_generators/electroshape.py # noqa: E501

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import ElectroShapeFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class ElectroShapeFeature(FeatureGenerator):
    name = "electroshape"

    N_FEATURES = 15

    def __init__(self, partial_charge_model: str = "formal") -> None:
        self._fp = ElectroShapeFingerprint(
            partial_charge_model=partial_charge_model, n_jobs=1
        )

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from ElectroShapeFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self.N_FEATURES)

    def placeholder_value(self) -> list[float]:
        return [0.0] * self.N_FEATURES
