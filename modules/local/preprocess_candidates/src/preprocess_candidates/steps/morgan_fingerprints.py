# modules/local/preprocess_candidates/src/preprocess_candidates/steps/fingerprints.py

from typing import Any

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol, rdFingerprintGenerator


class MorganFingerprintStep:
    name = "morgan_fingerprint"

    def __init__(self, morgan_radius: int, morgan_n_bits: int) -> None:
        self._mfp_gen: Any = None
        self._morgan_radius = morgan_radius
        self._morgan_n_bits = morgan_n_bits

    def init_worker(self) -> None:
        self._mfp_gen = rdFingerprintGenerator.GetMorganGenerator(
            radius=self._morgan_radius, fpSize=self._morgan_n_bits
        )

    def compute(self, mol: Mol) -> dict[str, Any]:
        if self._mfp_gen is None:
            raise RuntimeError(
                f"{self.name}: init_worker() must be called before compute()"
            )

        morgan_fingerprint = np.stack(self._mfp_gen.GetFingerprintAsNumPy(mol))

        return {"morgan_fingerprint": morgan_fingerprint}

    def failure_result(self) -> dict[str, Any]:
        return {"morgan_fingerprint": []}

    def output_fields(self) -> list[tuple[str, Any]]:
        return [("morgan_fingerprint", pa.list_(pa.uint8(), self._morgan_n_bits))]
