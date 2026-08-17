# modules/local/preprocess_candidates/src/preprocess_candidates/steps/__init__.py


from __future__ import annotations

from typing import Any

import pyarrow as pa
from rdkit.Chem import Descriptors

from .step import StepContext


class BasicDescriptorsStep:
    name = "basic_descriptors"

    def init_worker(self) -> None:
        pass

    def compute(self, ctx: StepContext) -> dict[str, Any]:
        return {
            "heavy_atom_count": ctx.mol.GetNumHeavyAtoms(),
            "molecular_weight": Descriptors.MolWt(ctx.mol),
        }

    def failure_result(self) -> dict[str, Any]:
        return {
            "heavy_atom_count": None,
            "molecular_weight": None,
        }

    def output_fields(self) -> list[tuple[str, Any]]:
        return [
            ("heavy_atom_count", pa.int16()),
            ("molecular_weight", pa.float32()),
        ]
