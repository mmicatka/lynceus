# modules/local/preprocess_candidates/src/preprocess_candidates/steps/conformers.py

from typing import Any

import blake3
import dimorphite_dl
import pyarrow as pa
from rdkit import Chem
from rdkit.Chem import AllChem, Mol


class ConformersStep:
    name = "conformers"

    def __init__(
        self,
        ph_min: float = 6.4,
        ph_max: float = 8.4,
        seed: int = 42,
    ) -> None:
        self._ph_min = ph_min
        self._ph_max = ph_max
        self._seed = seed

    def init_worker(self) -> None:
        pass

    def compute(self, mol: Mol) -> dict[str, Any]:
        smiles = Chem.MolToSmiles(mol)
        prot_smiles = self._select_protonation_state(smiles)

        embed_mol = Chem.MolFromSmiles(prot_smiles)
        if embed_mol is None:
            raise ValueError(f"Failed to reparse protonated SMILES: {prot_smiles!r}")

        embed_mol = Chem.AddHs(embed_mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = self._seed

        if AllChem.EmbedMolecule(embed_mol, params) != 0:
            raise ValueError("Conformer embedding failed")

        if AllChem.MMFFOptimizeMolecule(embed_mol) == -1:
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
