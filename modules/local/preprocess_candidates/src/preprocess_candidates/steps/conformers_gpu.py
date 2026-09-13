# modules/local/preprocess_candidates/src/preprocess_candidates/steps/conformers_gpu.py

import contextlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Generator

import blake3
import dimorphite_dl
import pyarrow as pa
from nvmolkit.autotune import load
from nvmolkit.embedMolecules import EmbedMolecules
from nvmolkit.mmffOptimization import MMFFOptimizeMoleculesConfs
from nvmolkit.types import HardwareOptions
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, Mol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

rdBase.DisableLog("rdApp.*")


@contextlib.contextmanager
def timed_stage(stage: str, logger: logging.Logger) -> Generator[None, None, None]:
    logger.info("METRIC stage=%s event=start", stage)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("METRIC stage=%s event=end elapsed_seconds=%.4f", stage, elapsed)


@contextlib.contextmanager
def _suppress_native_stderr():
    stderr_fd = 2
    saved_fd = os.dup(stderr_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(devnull_fd)
        os.close(saved_fd)


def _load_hardware_options(
    path: Path | None, fallback_batch_size: int
) -> HardwareOptions:
    if path is None:
        return HardwareOptions(batchSize=fallback_batch_size)
    if not path.exists():
        raise FileNotFoundError(f"Hardware options file not found: {path}")
    loaded = load(str(path))
    if not isinstance(loaded, HardwareOptions):
        raise TypeError(
            f"Expected HardwareOptions from {path}, got {type(loaded).__name__}"
        )
    return loaded


class ConformersGPUStep:
    name = "conformers"

    def __init__(
        self,
        ph_min: float = 6.4,
        ph_max: float = 8.4,
        seed: int = 42,
        optimize_max_iters: int = 50,
        embed_max_iters: int = 50,
        batch_size: int = 500,
        embed_hardware_options_path: Path | None = None,
        mmff_hardware_options_path: Path | None = None,
    ) -> None:
        rdBase.DisableLog("rdApp.*")
        self._ph_min = ph_min
        self._ph_max = ph_max
        self._optimize_max_iters = optimize_max_iters

        self._embed_params = AllChem.ETKDGv3()
        self._embed_params.randomSeed = seed
        self._embed_params.maxIterations = embed_max_iters
        self._embed_params.useRandomCoords = True

        self._embed_hardware_options = _load_hardware_options(
            embed_hardware_options_path, batch_size
        )
        self._mmff_hardware_options = _load_hardware_options(
            mmff_hardware_options_path, batch_size
        )

    def init_worker(self) -> None:
        pass

    def compute_batch(self, mols: list[Mol]) -> list[dict[str, Any] | None]:
        prot_smiles_list: list[str | None] = []
        embed_mols: list[Mol | None] = []

        prep_step_times = {
            "MolToSmiles": 0.0,
            "select_protonation": 0.0,
            "MolFromSmiles": 0.0,
            "AddHs": 0.0,
        }

        with timed_stage("conformers_prepare", logger):
            for mol in mols:
                try:
                    embed_mol, prot_smiles = self._prepare_embed_mol(
                        mol, prep_step_times
                    )
                except Exception:
                    embed_mols.append(None)
                    prot_smiles_list.append(None)
                    continue

                embed_mols.append(embed_mol)
                prot_smiles_list.append(prot_smiles)

        logger.info(
            "METRIC stage=conformers_prepare_steps event=summary "
            "MolToSmiles=%.4f select_protonation=%.4f MolFromSmiles=%.4f AddHs=%.4f",
            prep_step_times["MolToSmiles"],
            prep_step_times["select_protonation"],
            prep_step_times["MolFromSmiles"],
            prep_step_times["AddHs"],
        )

        live_indices = [i for i, m in enumerate(embed_mols) if m is not None]

        with timed_stage("conformers_embed_optimize", logger):
            embedded_indices = self._embed_and_optimize(embed_mols, live_indices)

        with timed_stage("conformers_build_results", logger):
            results = self._build_results(
                embed_mols, prot_smiles_list, embedded_indices
            )

        return results

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

    def _prepare_embed_mol(
        self, mol: Mol, step_times: dict[str, float]
    ) -> tuple[Mol, str]:
        t0 = time.perf_counter()
        smiles = Chem.MolToSmiles(mol)

        t1 = time.perf_counter()
        prot_smiles = self._select_protonation_state(smiles)

        t2 = time.perf_counter()
        embed_mol = Chem.MolFromSmiles(prot_smiles)
        if embed_mol is None:
            raise ValueError(f"Failed to reparse protonated SMILES: {prot_smiles!r}")

        t3 = time.perf_counter()
        result = Chem.AddHs(embed_mol)

        t4 = time.perf_counter()

        step_times["MolToSmiles"] += t1 - t0
        step_times["select_protonation"] += t2 - t1
        step_times["MolFromSmiles"] += t3 - t2
        step_times["AddHs"] += t4 - t3

        return result, prot_smiles

    def _embed_and_optimize(
        self, embed_mols: list[Mol | None], live_indices: list[int]
    ) -> set[int]:
        if not live_indices:
            return set()

        live_mols: list[Mol] = [
            embed_mols[i] for i in live_indices if embed_mols[i] is not None
        ]

        try:
            with _suppress_native_stderr():
                EmbedMolecules(
                    molecules=live_mols,
                    params=self._embed_params,
                    confsPerMolecule=1,
                    maxIterations=-1,
                    hardwareOptions=self._embed_hardware_options,
                )
        except Exception:
            return set()

        embedded_indices = {
            i for i, m in zip(live_indices, live_mols) if m.GetNumConformers() > 0
        }
        if not embedded_indices:
            return embedded_indices

        embedded_mols = [embed_mols[i] for i in embedded_indices]
        try:
            with _suppress_native_stderr():
                MMFFOptimizeMoleculesConfs(
                    embedded_mols,
                    maxIters=self._optimize_max_iters,
                    hardwareOptions=self._mmff_hardware_options,
                )
        except ValueError as exc:
            failed = exc.args[1] if len(exc.args) > 1 else {}
            failed_local = set(failed.get("none", [])) | set(
                failed.get("no_params", [])
            )
            embedded_list = list(embedded_indices)
            failed_global = {embedded_list[i] for i in failed_local}
            embedded_indices -= failed_global
        except Exception:
            return set()

        return embedded_indices

    def _build_results(
        self,
        embed_mols: list[Mol | None],
        prot_smiles_list: list[str | None],
        embedded_indices: set[int],
    ) -> list[dict[str, Any] | None]:
        results: list[dict[str, Any] | None] = []
        for i, embed_mol in enumerate(embed_mols):
            if i not in embedded_indices or embed_mol is None:
                results.append(None)
                continue

            sdf = Chem.MolToMolBlock(embed_mol)
            content_hash = f"blake3:{blake3.blake3(sdf.encode()).hexdigest()}"
            results.append(
                {
                    "protonated_smiles": prot_smiles_list[i],
                    "conformer_sdf": sdf,
                    "conformer_content_hash": content_hash,
                }
            )
        return results

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
