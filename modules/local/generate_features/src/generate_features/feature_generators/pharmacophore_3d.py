# modules/local/feature_generation/src/feature_generation/feature_generators/pharmacore_3d.py # noqa: E501

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import PharmacophoreFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class Pharmacophore3dFeature(FeatureGenerator):
    name = "pharmacophore_3d"

    DEFAULT_FP_SIZE = 1024

    def __init__(self, fp_size: int = DEFAULT_FP_SIZE) -> None:
        self._fp_size = fp_size
        self._fp = PharmacophoreFingerprint(
            fp_size=fp_size, use_3D=True, variant="folded", n_jobs=1, sparse=False
        )

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from PharmacophoreFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.uint8(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [0] * self._fp_size
