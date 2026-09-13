# modules/local/generate_conformers/src/generate_conformers/generate_conformers.py

import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Iterator

import dimorphite_dl
from rdkit import rdBase
from rdkit.Chem import AddHs, AllChem, Mol, MolFromSmiles, MolToMolBlock

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

MAX_PROTONATION_VARIANTS = 4
MAX_ITERS = 50

EMBED_PARAMS = AllChem.ETKDGv3()
EMBED_PARAMS.randomSeed = 1000
EMBED_PARAMS.maxIterations = MAX_ITERS
EMBED_PARAMS.useRandomCoords = True

OPTIMIZE_MAX_ITERS = 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


def _generate_protonated_smiles(smiles_list: list[str], max_variants: int) -> list[str]:
    res = []
    for _smiles in smiles_list:
        variants = dimorphite_dl.protonate_smiles(
            _smiles, validate_output=True, max_variants=max_variants
        )
        res.append(variants[0] if variants else _smiles)

    return res


def _prepare_mols(smiles_list: list[str]) -> list[Mol | None]:
    res = []
    for _smiles in smiles_list:
        try:
            mol = MolFromSmiles(_smiles)
            prepared_mol = AddHs(mol)
        except Exception:
            prepared_mol = None

        res.append(prepared_mol)

    return res


def _chunk(input: list, size: int) -> Iterator[list]:
    chunk = []
    for item in input:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _embed_and_optimize_mol(mol: Mol | None) -> Mol | None:
    if (
        mol is not None
        and AllChem.EmbedMolecule(mol, EMBED_PARAMS) != -1
        and AllChem.MMFFOptimizeMolecule(mol, maxIters=OPTIMIZE_MAX_ITERS) != -1
    ):
        return mol
    return None


def _prepare_embed_and_optimize_chunk(
    smiles_list: list[str], max_protonation_variants: int = MAX_PROTONATION_VARIANTS
) -> list[Mol | None]:
    protonated_smiles = _generate_protonated_smiles(
        smiles_list, max_protonation_variants
    )

    mols = _prepare_mols(protonated_smiles)
    return [_embed_and_optimize_mol(mol) for mol in mols]


def _prepare_embed_and_optimize(
    executor: ProcessPoolExecutor,
    smiles_list: list[str],
    chunk_size: int,
) -> list[Mol | None]:
    res: list[Mol | None] = []

    for chunk_mols in executor.map(
        _prepare_embed_and_optimize_chunk, _chunk(smiles_list, chunk_size)
    ):
        res.extend(chunk_mols)

    return res


def generate_conformers_chunk(
    executor: ProcessPoolExecutor,
    smiles_list: list[str],
    chunk_size: int = 50,
) -> list[str]:
    mols = _prepare_embed_and_optimize(executor, smiles_list, chunk_size)
    return [MolToMolBlock(mol) if mol else "" for mol in mols]
