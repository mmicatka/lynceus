# modules/local/surrogate_model/src/surrogate_model/features/fingerprints.py


from __future__ import annotations

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Avalon import pyAvalonTools
from rdkit.Chem import MACCSkeys, rdFingerprintGenerator

MORGAN_ECFP4_RADIUS = 2
MORGAN_ECFP4_BITS = 2048
MORGAN_ECFP6_RADIUS = 3
MORGAN_ECFP6_BITS = 2048
MACCS_BITS = 167  # RDKit's MACCS generator emits 167 bits; bit 0 is an unused pad bit.
AVALON_BITS = 512


def _fp_to_array(fp, n_bits: int) -> np.ndarray:
    arr = np.zeros((n_bits,), dtype=np.uint8)
    DataStructs.ConvertToNumpyArray(fp, arr)
    return arr


def morgan_fingerprint(
    mol: Chem.Mol, radius: int = MORGAN_ECFP4_RADIUS, n_bits: int = MORGAN_ECFP4_BITS
) -> np.ndarray:
    """Morgan (circular) fingerprint. Defaults to ECFP4 (radius=2, 2048 bits)."""
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=n_bits)
    return _fp_to_array(generator.GetFingerprint(mol), n_bits)


def maccs_fingerprint(mol: Chem.Mol) -> np.ndarray:
    """MACCS structural keys (167 bits as emitted by RDKit; bit 0 unused)."""
    return _fp_to_array(MACCSkeys.GenMACCSKeys(mol), MACCS_BITS)


def avalon_fingerprint(mol: Chem.Mol, n_bits: int = AVALON_BITS) -> np.ndarray:
    """Avalon fingerprint."""
    fp = pyAvalonTools.GetAvalonFP(mol, nBits=n_bits)
    return _fp_to_array(fp, n_bits)


def fingerprint_features(
    mol: Chem.Mol,
    *,
    include_ecfp6: bool = False,
    include_maccs: bool = False,
    include_avalon: bool = False,
) -> dict[str, np.ndarray]:
    features: dict[str, np.ndarray] = {
        "fp_ecfp4": morgan_fingerprint(
            mol, radius=MORGAN_ECFP4_RADIUS, n_bits=MORGAN_ECFP4_BITS
        ),
    }
    if include_ecfp6:
        features["fp_ecfp6"] = morgan_fingerprint(
            mol, radius=MORGAN_ECFP6_RADIUS, n_bits=MORGAN_ECFP6_BITS
        )
    if include_maccs:
        features["fp_maccs"] = maccs_fingerprint(mol)
    if include_avalon:
        features["fp_avalon"] = avalon_fingerprint(mol)
    return features
