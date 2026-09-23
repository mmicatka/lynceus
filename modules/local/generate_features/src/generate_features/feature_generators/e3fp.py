# modules/local/feature_generation/src/feature_generation/feature_generators/e3fp.py

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol
from skfp.fingerprints import E3FPFingerprint

from generate_features.feature_generators.feature_generator import FeatureGenerator


class E3FPFeature(FeatureGenerator):
    name = "e3fp"

    DEFAULT_FP_SIZE = 1024
    DEFAULT_LEVEL = 5

    def __init__(
        self, fp_size: int = DEFAULT_FP_SIZE, level: int = DEFAULT_LEVEL
    ) -> None:
        self._fp_size = fp_size
        self._fp = E3FPFingerprint(fp_size=fp_size, n_jobs=1, sparse=False, level=level)

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        for idx, mol in enumerate(batch):
            if mol is not None and (
                not mol.HasProp("_Name") or not mol.GetProp("_Name").strip()
            ):
                mol.SetProp("_Name", f"mol_{idx}")

        fingerprints = self._fp.transform(batch)
        if not isinstance(fingerprints, np.ndarray):
            raise RuntimeError(
                "expected dense ndarray from E3FPFingerprint.transform,"
                f" got {type(fingerprints)}"
            )
        return [row.tolist() for row in fingerprints]

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.uint8(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [0] * self._fp_size
