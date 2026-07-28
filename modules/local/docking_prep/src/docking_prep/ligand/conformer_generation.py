# modules/local/docking_prep/src/docking_prep/ligand/conformer_generation.py


import logging
import math
import sys
from dataclasses import dataclass

import dimorphite_dl
from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.rdchem import Mol

from docking_prep.ligand.models import ConformerRecord, Conformers
from docking_prep.utils import content_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddedConformer:
    conf_id: int  # RDKit's internal conformer id on the working Mol
    mmff_energy: float


def _select_protonation_state(
    smiles: str,
    ph_min: float = 6.4,
    ph_max: float = 8.4,
) -> str:
    variants = dimorphite_dl.protonate_smiles(
        smiles, ph_min=ph_min, ph_max=ph_max, validate_output=True
    )
    if not variants:
        raise ValueError(
            f"Dimorphite-DL returned no protonation states for SMILES: {smiles!r}"
        )

    def sort_key(variant_smiles: str) -> tuple[int, str]:
        mol = Chem.MolFromSmiles(variant_smiles)
        if mol is None:
            return (10**6, variant_smiles)
        formal_charge = Chem.GetFormalCharge(mol)
        canonical = Chem.MolToSmiles(mol)
        return (abs(formal_charge), canonical)

    return min(variants, key=sort_key)


def _embed_and_rank_conformers(
    smiles: str,
    n_confs: int,
    random_seed: int = 1000,
    max_iters: int = 500,
) -> tuple[Mol, list[EmbeddedConformer]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    params.useRandomCoords = True
    params.pruneRmsThresh = -1.0  # no built-in pruning; we prune explicitly later

    conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=n_confs, params=params))
    if not conf_ids:
        raise ValueError(f"RDKit ETKDG embedding failed for SMILES: {smiles!r}")

    mmff_props = AllChem.MMFFGetMoleculeProperties(mol)
    if mmff_props is None:
        raise ValueError(
            f"MMFF94 parameters unavailable for SMILES: {smiles!r} "
            "(unsupported atom types for MMFF)"
        )

    embedded: list[EmbeddedConformer] = []
    for conf_id in conf_ids:
        ff = AllChem.MMFFGetMoleculeForceField(mol, mmff_props, confId=conf_id)
        if ff is None:
            logger.warning(
                "Could not construct MMFF94 force field for conformer %d of %r",
                conf_id,
                smiles,
            )
            continue
        converged = ff.Minimize(maxIts=max_iters)
        if converged != 0:
            logger.warning(
                "MMFF94 minimization did not fully converge within %d iterations "
                "for conformer %d of %r; keeping best available geometry.",
                max_iters,
                conf_id,
                smiles,
            )
        energy = ff.CalcEnergy()
        embedded.append(EmbeddedConformer(conf_id=conf_id, mmff_energy=energy))

    embedded.sort(key=lambda e: e.mmff_energy)
    return mol, embedded


def _unaligned_rmsd(
    mol: Mol, conf_id_1: int, conf_id_2: int, heavy_atom_only: bool = True
) -> float:
    c1 = mol.GetConformer(conf_id_1)
    c2 = mol.GetConformer(conf_id_2)
    sq_diffs = []
    for atom in mol.GetAtoms():
        if heavy_atom_only and atom.GetAtomicNum() == 1:
            continue
        i = atom.GetIdx()
        p1, p2 = c1.GetAtomPosition(i), c2.GetAtomPosition(i)
        sq_diffs.append((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)
    if not sq_diffs:
        return 0.0
    return math.sqrt(sum(sq_diffs) / len(sq_diffs))


def _prune_and_select_top_n(
    mol: Mol,
    embedded: list[EmbeddedConformer],
    keep_top_n: int,
    rmsd_prune_threshold: float,
) -> list[EmbeddedConformer]:
    kept: list[EmbeddedConformer] = []
    for candidate in embedded:
        if len(kept) >= keep_top_n:
            break
        is_duplicate = any(
            _unaligned_rmsd(mol, candidate.conf_id, k.conf_id) < rmsd_prune_threshold
            for k in kept
        )
        if not is_duplicate:
            kept.append(candidate)
    return kept


def conformer_to_pdbqt(mol: Mol, conf_id: int, name: str) -> str:
    mol.SetProp("_Name", name)
    preparator = MoleculePreparation()
    setups = preparator.prepare(mol, conformer_id=conf_id)
    if not setups:
        raise ValueError("Meeko produced no molecule setups for this conformer")

    setup = setups[0]
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setup)
    if not is_ok:
        raise ValueError(f"Meeko PDBQT writing failed: {error_msg}")
    return pdbqt_string


def generate_conformers(
    candidate_id: str,
    smiles: str,
    ph_min: float,
    ph_max: float,
    n_confs: int,
    keep_top_n: int,
    rmsd_prune_threshold: float,
    random_seed: int,
) -> Conformers:
    try:
        protonated_smiles = _select_protonation_state(
            smiles, ph_min=ph_min, ph_max=ph_max
        )
        mol, embedded = _embed_and_rank_conformers(
            protonated_smiles, n_confs=n_confs, random_seed=random_seed
        )
        kept = _prune_and_select_top_n(mol, embedded, keep_top_n, rmsd_prune_threshold)

        conformers: list[ConformerRecord] = []
        for rank, e in enumerate(kept):
            pdbqt_text = conformer_to_pdbqt(
                mol, e.conf_id, name=f"{candidate_id}_rank{rank}"
            )
            cid = content_id(pdbqt_text.encode("utf-8"))
            conformers.append(
                ConformerRecord(
                    conformer_id=cid,
                    pdbqt_text=pdbqt_text,
                    mmff_energy=e.mmff_energy,
                    rank=rank,
                )
            )

        return Conformers(
            id=candidate_id,
            source_smiles=smiles,
            protonated_smiles=protonated_smiles,
            conformers=conformers,
            n_confs_requested=n_confs,
            n_confs_embedded=len(embedded),
            random_seed=random_seed,
            ph_min=ph_min,
            ph_max=ph_max,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - intentionally broad: isolate per-candidate failures
        return Conformers(
            id=candidate_id,
            source_smiles=smiles,
            protonated_smiles=None,
            error=str(exc),
        )
