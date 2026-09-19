# modules/local/feature_generation/src/feature_generation/feature_generators/topological_torsion.py # noqa: E501

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import TopologicalTorsionFingerprint

from feature_generation.feature_generators.feature_generator import FeatureGenerator


class TopologicalTorsionFeature(FeatureGenerator):
    name = "topological_torsion"

    DEFAULT_FP_SIZE = 2048

    def __init__(self, fp_size: int = DEFAULT_FP_SIZE) -> None:
        self._fp_size = fp_size
        self._fp = TopologicalTorsionFingerprint(
            fp_size=fp_size, count=True, n_jobs=1, sparse=False
        )

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from TopologicalTorsionFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.uint16(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [0] * self._fp_size
