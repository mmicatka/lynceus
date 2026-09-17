# modules/local/feature_generation/src/feature_generation/feature_generators/cns_mpo.py

import pyarrow as pa
from rdkit.Chem import Mol, rdMolDescriptors

from feature_generation.feature_generators.feature_generator import FeatureGenerator


def _lerp(v: float, lo: float, hi: float, s_lo: float, s_hi: float) -> float:
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return s_lo + (s_hi - s_lo) * t


def _d_clogd(v: float) -> float:
    if 2.0 <= v <= 4.0:
        return 1.0
    if v < 0.0 or v > 5.0:
        return 0.0
    if v < 2.0:
        return _lerp(v, 0.0, 2.0, 0.0, 1.0)
    return _lerp(v, 4.0, 5.0, 1.0, 0.0)


def _d_molecular_weight(v: float) -> float:
    if v <= 360.0:
        return 1.0
    if v >= 500.0:
        return 0.0
    return _lerp(v, 360.0, 500.0, 1.0, 0.0)


def _d_total_polar_surface_area(v: float) -> float:
    if 40.0 <= v <= 90.0:
        return 1.0
    if v < 20.0 or v > 120.0:
        return 0.0
    if v < 40.0:
        return _lerp(v, 20.0, 40.0, 0.0, 1.0)
    return _lerp(v, 90.0, 120.0, 1.0, 0.0)


def _d_hydrogen_bond_donors(v: float) -> float:
    if v <= 0.0:
        return 1.0
    if v >= 3.0:
        return 0.0
    return _lerp(v, 0.0, 3.0, 1.0, 0.0)


def _d_basic_center(has_protonated_basic_n: bool) -> float:
    return 0.0 if has_protonated_basic_n else 1.0


def _has_protonated_basic_nitrogen(mol: Mol) -> bool:
    return any(
        atom.GetSymbol() == "N" and atom.GetFormalCharge() > 0
        for atom in mol.GetAtoms()
    )


class CNSMPOFeature(FeatureGenerator):
    name = "cns_mpo"

    def __init__(self) -> None:
        self._fp_size = 5

    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]:
        results = []
        for mol in batch:
            if mol is None:
                results.append(self.placeholder_value())
                continue

            try:
                mw = rdMolDescriptors.CalcExactMolWt(mol)
                clogd = rdMolDescriptors.CalcCrippenDescriptors(mol)[0]
                tpsa = rdMolDescriptors.CalcTPSA(mol)
                hbd = rdMolDescriptors.CalcNumHBD(mol)
                has_protonated_basic_n = _has_protonated_basic_nitrogen(mol)

                cns_mpo_score = (
                    _d_clogd(clogd)
                    + _d_clogd(
                        clogd
                    )  # stand-in for the neutral-CLogP term, already protonated
                    + _d_molecular_weight(mw)
                    + _d_total_polar_surface_area(tpsa)
                    + _d_hydrogen_bond_donors(hbd)
                    + _d_basic_center(has_protonated_basic_n)
                )

                results.append([mw, clogd, tpsa, float(hbd), cns_mpo_score])

            except Exception:
                results.append(self.placeholder_value())

        return results

    def feature_field_name(self) -> str:
        return self.name

    def feature_field_type(self) -> pa.DataType:
        return pa.list_(pa.float32(), self._fp_size)

    def placeholder_value(self) -> list[float]:
        return [float("nan")] * self._fp_size
