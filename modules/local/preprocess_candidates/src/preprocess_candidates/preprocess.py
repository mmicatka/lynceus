# modules/local/preprocess_candidates/src/preprocess_candidates/preprocess.py

from typing import Any

from rdkit import Chem

from preprocess_candidates.steps.descriptors import DescriptorsStep

from .steps.step import Step

DEFAULT_PIPELINE_STEPS: list[Step] = [
    DescriptorsStep(),
    # MorganFingerprintStep(radius=2, n_bits=2048),
    # CnsMpoStep(),
    # PainsFilterStep(),
    # ProtonationStateStep(ph_min=6.4, ph_max=8.4),
    # ConformerGenerateStep(random_seed=1000),
]


def preprocess(smiles: str, steps: list[Step]) -> dict[str, Any]:
    mol: Chem.Mol | None = Chem.MolFromSmiles(smiles)

    res: dict[str, Any] = {"smiles": smiles, "parse_ok": mol is not None}

    if mol is None:
        for _step in steps:
            res.update(_step.failure_result())
        return res

    for _step in steps:
        try:
            res.update(mol)
        except Exception:
            res.update(_step.failure_result())

    return res
