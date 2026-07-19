# libs/lynceus-chem/src/lynceus_chem/preprocess/cns_mpo.py

import math
from typing import Optional

from rdkit import Chem
from rdkit.Chem import (
    Descriptors,
    rdMolDescriptors,
)

# (smarts, pKa, label)
_PKA_RULES: tuple[tuple[str, float, str], ...] = (
    ("[NX3;H2][CX3](=[NH])[NX3;H2]", 13.5, "guanidine"),
    ("[NX3;H1,H2][CX3](=[NH])[NX3;H1,H2]", 12.5, "guanidine_sub"),
    ("[NX3;H1,H2][CX3]=[NX2]", 11.5, "amidine"),
    ("[N;R;X3;H1;!$(NC=O)]1CCCC1", 11.0, "pyrrolidine"),
    ("[N;R;X3;H1;!$(NC=O)]1CCCCC1", 10.8, "piperidine"),
    ("[NX3;H2;!$(NC=O);!$(NS(=O))]", 10.5, "primary_amine"),
    ("[N;R;X3;H0;!$(NC=O)]1CCCC1", 10.2, "N-sub_pyrrolidine"),
    ("[N;R;X3;H0;!$(NC=O)]1CCCCC1", 10.0, "N-sub_piperidine"),
    ("[NX3;H0;!$(NC=O);!$(NS(=O))]([CX4])([CX4])[CX4]", 9.8, "tertiary_amine"),
    ("[N;R;X3;!$(NC=O)]1CC[NH]CC1", 9.8, "piperazine_NH"),
    ("[NX3;H1;!$(NC=O);!$(NS(=O))][CX4][CX4]", 9.5, "secondary_amine"),
    ("[NX3;H1;!$(NC=O);!$(NS(=O))]", 9.0, "secondary_amine_gen"),
    ("[NX3;H0;!$(NC=O);!$(NS(=O))]([CX4])[CX4]", 9.0, "tertiary_amine_2sub"),
    ("[N;R;X3;!$(NC=O)]1CCN(CC1)", 8.7, "piperazine_N"),
    ("[N;R;X3;H1;!$(NC=O)]1CCOCC1", 8.3, "morpholine"),
    ("[N;R;X3;H0;!$(NC=O)]1CCOCC1", 7.4, "N-sub_morpholine"),
    ("c1cnc[nH]1", 6.9, "imidazole"),
    ("c1ccnc(N)c1", 6.7, "aminopyridine"),
    ("c1ccncc1", 5.2, "pyridine"),
    ("c1cnc(n1)", 5.0, "imidazole_sub"),
    ("[NH2]c1ccccc1", 4.6, "aniline"),
    ("[NH;!$(NC=O)]c1ccccc1", 3.8, "N-sub_aniline"),
    ("[N;H0;!$(NC=O)]c1ccccc1", 2.5, "N_diaryl_amine"),
    ("[NH;$(NC=O)]", -1.0, "amide_NH"),
    ("[NH;$(NS(=O))]", -1.0, "sulfonamide_NH"),
)

_compiled: list[tuple[Chem.Mol, float]] | None = None


def _get_compiled() -> list[tuple[Chem.Mol, float]]:
    global _compiled
    if _compiled is None:
        _compiled = []
        for smarts, pka, label in _PKA_RULES:
            pat = Chem.MolFromSmarts(smarts)
            if pat is None:
                raise ValueError(f"Invalid SMARTS for rule '{label}': {smarts}")
            _compiled.append((pat, pka))
    return _compiled


def most_basic_pka(mol: Chem.Mol) -> Optional[float]:
    """Estimated pKa of the most basic centre, or None if no basic nitrogen."""
    best: Optional[float] = None
    for pat, pka in _get_compiled():
        if mol.HasSubstructMatch(pat):
            if best is None or pka > best:
                best = pka
    return best


# ---------------------------------------------------------------------------
# Wager 2010 desirability functions
# ---------------------------------------------------------------------------


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


def _d_mw(v: float) -> float:
    if v <= 360.0:
        return 1.0
    if v >= 500.0:
        return 0.0
    return _lerp(v, 360.0, 500.0, 1.0, 0.0)


def _d_tpsa(v: float) -> float:
    if 40.0 <= v <= 90.0:
        return 1.0
    if v < 20.0 or v > 120.0:
        return 0.0
    if v < 40.0:
        return _lerp(v, 20.0, 40.0, 0.0, 1.0)
    return _lerp(v, 90.0, 120.0, 1.0, 0.0)


def _d_hbd(v: float) -> float:
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


def cns_mpo_from_mol(mol: Chem.Mol) -> dict[str, float | None]:
    """Compute CNS-MPO score and all component properties/desirabilities."""
    clogp = Descriptors.MolLogP(mol)
    mw = Descriptors.ExactMolWt(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    hbd = float(Chem.rdMolDescriptors.CalcNumHBD(mol))
    pka = most_basic_pka(mol)

    clogd = (
        clogp - math.log10(1.0 + 10.0 ** (pka - 7.4))
        if pka is not None and pka > 0
        else clogp
    )

    d_cp = _d_clogp(clogp)
    d_cd = _d_clogd(clogd)
    d_mw = _d_mw(mw)
    d_tp = _d_tpsa(tpsa)
    d_hb = _d_hbd(hbd)
    d_pk = _d_pka(pka)

    return {
        "clogp": clogp,
        "clogd": clogd,
        "mw": mw,
        "tpsa": tpsa,
        "hbd": hbd,
        "pka": pka,
        "clogp_d": d_cp,
        "clogd_d": d_cd,
        "mw_d": d_mw,
        "tpsa_d": d_tp,
        "hbd_d": d_hb,
        "pka_d": d_pk,
        "cns_mpo": d_cp + d_cd + d_mw + d_tp + d_hb + d_pk,
    }
