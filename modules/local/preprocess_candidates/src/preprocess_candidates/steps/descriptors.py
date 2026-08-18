# modules/local/preprocess_candidates/src/preprocess_candidates/steps/descriptors.py

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import pyarrow as pa
from rdkit.Chem import Descriptors, Mol, MolFromSmarts, rdMolDescriptors


class DescriptorsStep:
    name = "basic_descriptors"

    def __init__(self) -> None:
        self._compiled_pka_rules: list[tuple[Mol, float]] = []

    def init_worker(self) -> None:
        for rule in _PKA_RULES:
            pattern = MolFromSmarts(rule.smarts)
            if pattern is None:
                raise ValueError(
                    f"Invalid SMARTS for pKa rule '{rule.label}': {rule.smarts}"
                )
            self._compiled_pka_rules.append((pattern, rule.pka))

    def compute(self, mol: Mol) -> dict[str, Any]:
        if self._compiled_pka_rules is None:
            raise RuntimeError(
                f"{self.name}: init_worker() must be called before compute()"
            )

        molecular_weight = Descriptors.MolWt(mol)

        clogp = Descriptors.MolLogP(mol)
        pka = _most_basic_pka(mol, self._compiled_pka_rules)
        has_basic_center = pka is not None and pka > 0
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        clogd = (
            clogp - math.log10(1.0 + 10.0 ** (pka - 7.4)) if has_basic_center else clogp
        )
        hydrogen_bond_donors = rdMolDescriptors.CalcNumHBD(mol)
        return {
            "heavy_atom_count": mol.GetNumHeavyAtoms(),
            "molecular_weight": molecular_weight,
            "calculated_partition_coefficient": clogp,
            "calculated_distribution_coefficient": clogd,
            "has_basic_center": has_basic_center,
            "topological_polar_surface_area": tpsa,
            "hydrogen_bond_donors": hydrogen_bond_donors,
            "pka": pka,
            "cns_mpo": cns_mpo(
                clogp, clogd, molecular_weight, tpsa, hydrogen_bond_donors, pka
            ),
        }

    def failure_result(self) -> dict[str, Any]:
        return {
            "heavy_atom_count": None,
            "molecular_weight": None,
            "calculated_partition_coefficient": None,
            "calculated_distribution_coefficient": None,
            "has_basic_center": None,
            "topological_polar_surface_area": None,
            "hydrogen_bond_donors": None,
            "pka": None,
            "cns_mpo": None,
        }

    def output_fields(self) -> list[tuple[str, Any]]:
        return [
            ("heavy_atom_count", pa.int16()),
            ("molecular_weight", pa.float32()),
            ("calculated_partition_coefficient", pa.float32()),
            ("calculated_distribution_coefficient", pa.float32()),
            ("has_basic_center", pa.bool_()),
            ("topological_polar_surface_area", pa.float32()),
            ("hydrogen_bond_donors", pa.int16()),
            ("pka", pa.float32()),
            ("cns_mpo", pa.float32()),
        ]


@dataclass(frozen=True)
class PkaRule:
    smarts: str
    pka: float
    label: str


# FIXME: rule selection is "highest pKa among all substructure matches", not
# "most specific pattern wins". Several patterns overlap (e.g. secondary_amine
# vs secondary_amine_gen, guanidine vs guanidine_sub) and are only implicitly
# disambiguated by pKa ordering. Verify this against a reference dataset
# (e.g. DataWarrior or a curated basic-pKa benchmark) before trusting output.
_PKA_RULES: tuple[PkaRule, ...] = (
    PkaRule("[NX3;H2][CX3](=[NH])[NX3;H2]", 13.5, "guanidine"),
    PkaRule("[NX3;H1,H2][CX3](=[NH])[NX3;H1,H2]", 12.5, "guanidine_sub"),
    PkaRule("[NX3;H1,H2][CX3]=[NX2]", 11.5, "amidine"),
    PkaRule("[N;R;X3;H1;!$(NC=O)]1CCCC1", 11.0, "pyrrolidine"),
    PkaRule("[N;R;X3;H1;!$(NC=O)]1CCCCC1", 10.8, "piperidine"),
    PkaRule("[NX3;H2;!$(NC=O);!$(NS(=O))]", 10.5, "primary_amine"),
    PkaRule("[N;R;X3;H0;!$(NC=O)]1CCCC1", 10.2, "N-sub_pyrrolidine"),
    PkaRule("[N;R;X3;H0;!$(NC=O)]1CCCCC1", 10.0, "N-sub_piperidine"),
    PkaRule("[NX3;H0;!$(NC=O);!$(NS(=O))]([CX4])([CX4])[CX4]", 9.8, "tertiary_amine"),
    PkaRule("[N;R;X3;!$(NC=O)]1CC[NH]CC1", 9.8, "piperazine_NH"),
    PkaRule("[NX3;H1;!$(NC=O);!$(NS(=O))][CX4][CX4]", 9.5, "secondary_amine"),
    PkaRule("[NX3;H1;!$(NC=O);!$(NS(=O))]", 9.0, "secondary_amine_gen"),
    PkaRule("[NX3;H0;!$(NC=O);!$(NS(=O))]([CX4])[CX4]", 9.0, "tertiary_amine_2sub"),
    PkaRule("[N;R;X3;!$(NC=O)]1CCN(CC1)", 8.7, "piperazine_N"),
    PkaRule("[N;R;X3;H1;!$(NC=O)]1CCOCC1", 8.3, "morpholine"),
    PkaRule("[N;R;X3;H0;!$(NC=O)]1CCOCC1", 7.4, "N-sub_morpholine"),
    PkaRule("c1cnc[nH]1", 6.9, "imidazole"),
    PkaRule("c1ccnc(N)c1", 6.7, "aminopyridine"),
    PkaRule("c1ccncc1", 5.2, "pyridine"),
    PkaRule("c1cnc(n1)", 5.0, "imidazole_sub"),
    PkaRule("[NH2]c1ccccc1", 4.6, "aniline"),
    PkaRule("[NH;!$(NC=O)]c1ccccc1", 3.8, "N-sub_aniline"),
    PkaRule("[N;H0;!$(NC=O)]c1ccccc1", 2.5, "N_diaryl_amine"),
    PkaRule("[NH;$(NC=O)]", -1.0, "amide_NH"),
    PkaRule("[NH;$(NS(=O))]", -1.0, "sulfonamide_NH"),
)


def _most_basic_pka(
    mol: Mol, compiled_rules: list[tuple[Mol, float]]
) -> Optional[float]:
    best: Optional[float] = None
    for pattern, pka in compiled_rules:
        if mol.HasSubstructMatch(pattern) and (best is None or pka > best):
            best = pka
    return best


def _lerp(v: float, lo: float, hi: float, s_lo: float, s_hi: float) -> float:
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return s_lo + (s_hi - s_lo) * t


def _d_clogp(v: float) -> float:
    if v <= 3.0:
        return 1.0
    if v >= 5.0:
        return 0.0
    return _lerp(v, 3.0, 5.0, 1.0, 0.0)


def _d_clogd(v: float) -> float:
    if v <= 2.0:
        return 1.0
    if v >= 4.0:
        return 0.0
    return _lerp(v, 2.0, 4.0, 1.0, 0.0)


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


def _d_pka(v: Optional[float]) -> float:
    if v is None or v <= 8.0:
        return 1.0
    if v >= 10.0:
        return 0.0
    return _lerp(v, 8.0, 10.0, 1.0, 0.0)


def cns_mpo(
    clogp: float,
    clogd: float,
    molecular_weight: float,
    total_polar_surface_area: float,
    hydrogen_bond_donors: int,
    pka: float,
) -> float:
    return (
        _d_clogp(clogp)
        + _d_clogd(clogd)
        + _d_molecular_weight(molecular_weight)
        + _d_total_polar_surface_area(total_polar_surface_area)
        + _d_hydrogen_bond_donors(hydrogen_bond_donors)
        + _d_pka(pka)
    )
