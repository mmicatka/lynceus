# modules/local/preprocess_candidates/src/preprocess_candidates/steps/conformers.py

import contextlib
import logging
import sys
import time
from typing import Any, Generator

import blake3
import dimorphite_dl
import pyarrow as pa
from rdkit import Chem
from rdkit.Chem import AllChem, Mol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def timed_stage(stage: str, logger: logging.Logger) -> Generator[None, None, None]:
    logger.info("METRIC stage=%s event=start", stage)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("METRIC stage=%s event=end elapsed_seconds=%.4f", stage, elapsed)


class ConformersCPUStep:
    name = "conformersCPU"

    def __init__(
        self,
        ph_min: float = 6.4,
        ph_max: float = 8.4,
        seed: int = 42,
        optimize_max_iters: int = 50,
        embed_max_iters: int = 50,
    ) -> None:
        self._ph_min = ph_min
        self._ph_max = ph_max
        self._optimize_max_iters = optimize_max_iters

        self._embed_params = AllChem.ETKDGv3()
        self._embed_params.randomSeed = seed
        self._embed_params.maxIterations = embed_max_iters

    def init_worker(self) -> None:
        pass

    def compute_batch(self, mols: list[Chem.Mol]) -> list[dict[str, Any] | None]:
        results = []
        for mol in mols:
            try:
                results.append(self._compute_one(mol))
            except Exception:
                results.append(None)
        return results

    def _compute_one(self, mol: Mol) -> dict[str, Any]:
        smiles = Chem.MolToSmiles(mol)
        prot_smiles = self._select_protonation_state(smiles)
        embed_mol = Chem.MolFromSmiles(prot_smiles)

        if embed_mol is None:
            raise ValueError(f"Failed to reparse protonated SMILES: {prot_smiles!r}")

        embed_mol = Chem.AddHs(embed_mol)

        if AllChem.EmbedMolecule(embed_mol, self._embed_params) != 0:
            raise ValueError("Conformer embedding failed")

        if (
            AllChem.MMFFOptimizeMolecule(embed_mol, maxIters=self._optimize_max_iters)
            == -1
        ):
            raise ValueError("MMFF94 minimization failed")

        sdf = Chem.MolToMolBlock(embed_mol)
        content_hash = f"blake3:{blake3.blake3(sdf.encode()).hexdigest()}"

        return {
            "protonated_smiles": prot_smiles,
            "conformer_sdf": sdf,
            "conformer_content_hash": content_hash,
        }

    def failure_result(self) -> dict[str, Any]:
        return {
            "protonated_smiles": None,
            "conformer_sdf": None,
            "conformer_content_hash": None,
        }

    def output_fields(self) -> list[tuple[str, Any]]:
        return [
            ("protonated_smiles", pa.string()),
            ("conformer_sdf", pa.string()),
            ("conformer_content_hash", pa.string()),
        ]

    def _select_protonation_state(self, smiles: str) -> str:
        variants = dimorphite_dl.protonate_smiles(
            smiles, ph_min=self._ph_min, ph_max=self._ph_max, validate_output=True
        )
        if not variants:
            raise ValueError(
                f"Dimorphite-DL returned no protonation states for SMILES: {smiles!r}"
            )

        def sort_key(variant_smiles: str) -> tuple[int, str]:
            variant_mol = Chem.MolFromSmiles(variant_smiles)
            if variant_mol is None:
                return (10**6, variant_smiles)
            formal_charge = Chem.GetFormalCharge(variant_mol)
            canonical = Chem.MolToSmiles(variant_mol)
            return (abs(formal_charge), canonical)

        return min(variants, key=sort_key)
