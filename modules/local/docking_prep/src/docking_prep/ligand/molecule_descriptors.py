# modules/local/docking_prep/src/docking_prep/ligand/molecule_desciptors.py

# TODO: Refactor this into pre-processing, will require conformer generation.


from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors


class MolDescriptorError(Exception):
    """Raised when descriptor calculation fails for a given mol/conformer."""


def compute_mol_geometry_descriptors(
    mol: Chem.Mol,
    include_autocorr3d: bool = True,
) -> dict[str, float]:
    if mol is None:
        raise MolDescriptorError("Cannot compute descriptors: mol is None.")
    if mol.GetNumConformers() == 0:
        raise MolDescriptorError("Cannot compute descriptors: mol has no conformer.")

    try:
        features: dict[str, float] = {
            "radius_of_gyration": rdMolDescriptors.CalcRadiusOfGyration(mol),
            "pmi1": rdMolDescriptors.CalcPMI1(mol),
            "pmi2": rdMolDescriptors.CalcPMI2(mol),
            "pmi3": rdMolDescriptors.CalcPMI3(mol),
            "pmi1_normalized": rdMolDescriptors.CalcNPR1(mol),
            "pmi2_normalized": rdMolDescriptors.CalcNPR2(mol),
            "asphericity": rdMolDescriptors.CalcAsphericity(mol),
            "eccentricity": rdMolDescriptors.CalcEccentricity(mol),
            "spherocity_index": rdMolDescriptors.CalcSpherocityIndex(mol),
        }
    except Exception as exc:
        raise MolDescriptorError(f"Shape descriptor calculation failed: {exc}") from exc

    if include_autocorr3d:
        try:
            autocorr = rdMolDescriptors.CalcAUTOCORR3D(mol)
        except Exception as exc:
            raise MolDescriptorError(f"AUTOCORR3D calculation failed: {exc}") from exc
        features.update({f"autocorr3d_{i}": float(v) for i, v in enumerate(autocorr)})

    return features
