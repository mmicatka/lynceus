# modules/local/docking_prep/docking-prep/src/docking_prep/prepare_ensemble.py

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import gemmi
from protein_conformational_ensemble.ensemble import Ensemble, load_ensemble
from protein_conformational_ensemble.models import ConformationalState

from docking_prep.ensemble.models import (
    EnsembleMemberPrepResult,
    EnsemblePrepParams,
    EnsemblePrepResults,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


_TEMPLATE_FAILURE_PREFIX = "- Template matching failed for: "


class ReceptorPrepError(Exception):
    """Base class for all `receptor_prep` errors."""


class ResidueTemplateError(ReceptorPrepError):
    def __init__(self, member_id: str, failed_residues: list[str]) -> None:
        self.member_id = member_id
        self.failed_residues = failed_residues
        super().__init__(
            f"Residue template matching failed for member '{member_id}': "
            f"{', '.join(failed_residues)}. Pass allow_bad_residues=True to "
            f"drop these residues instead of raising (they will be recorded "
            f"as warnings on the result)."
        )


class ReceptorPrepError(ReceptorPrepError):
    def __init__(self, member_id: str, returncode: int, stderr: str) -> None:
        self.member_id = member_id
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"mk_prepare_receptor.py failed for member '{member_id}' "
            f"(exit code {returncode}):\n{stderr}"
        )


def _parse_dropped_residues(stderr: str) -> list[str]:
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith(_TEMPLATE_FAILURE_PREFIX):
            remainder = line[len(_TEMPLATE_FAILURE_PREFIX) :]
            list_text = remainder[: remainder.index("]") + 1]
            residues = [
                token.strip().strip("'\"")
                for token in list_text.strip("[]").split(",")
                if token.strip()
            ]
            return residues
    return []


def prep_cif_with_gemmi(input_cif_path: str, output_pdb_path: str) -> str:
    """Strip waters and non-essential heteroatoms from a CIF, write as PDB."""
    cif_doc = gemmi.cif.read_file(input_cif_path)
    structure = gemmi.make_structure_from_block(cif_doc.sole_block())
    structure.remove_waters()

    keep_list = {"ZN", "MG", "CA", "FE", "HEM"}

    for model in structure:
        for chain in model:
            for i in reversed(range(len(chain))):
                res = chain[i]
                if not res.entity_type == gemmi.EntityType.Polymer:
                    if res.name not in keep_list:
                        del chain[i]

    structure.write_pdb(output_pdb_path)

    return output_pdb_path


def _prepare_structure(
    root_path: Path,
    conformational_state: ConformationalState,
    output: Path,
    params: EnsemblePrepParams,
) -> EnsembleMemberPrepResult:
    member_id = conformational_state.id
    output_stem = output / member_id
    expected_pdbqt = output_stem.with_suffix(".pdbqt")
    structure_path = root_path / conformational_state.structure.uri

    logger.info(
        "conformational_state: %s path: %s",
        member_id,
        structure_path,
    )

    try:
        prepped_pdb_path = output_stem.with_suffix(".prepped.pdb")
        prep_cif_with_gemmi(
            input_cif_path=str(structure_path),
            output_pdb_path=str(prepped_pdb_path),
        )

        command = [
            sys.executable,
            "-m",
            "meeko.cli.mk_prepare_receptor",
            "-i",
            str(prepped_pdb_path),
            "-o",
            str(output_stem),
            "-p",  # rigid-only PDBQT output
            "--default_altloc",
            params.default_altloc,
        ]
        if params.allow_bad_residues:
            command += ["--allow_bad_res"]

        completed = subprocess.run(command, capture_output=True, text=True)

        dropped_residues = _parse_dropped_residues(
            completed.stderr
        ) or _parse_dropped_residues(completed.stdout)

        if completed.returncode != 0:
            if dropped_residues and not params.allow_bad_residues:
                raise ResidueTemplateError(
                    member_id=member_id,
                    failed_residues=dropped_residues,
                )
            raise ReceptorPrepError(
                member_id=member_id,
                returncode=completed.returncode,
                stderr=completed.stderr or completed.stdout,
            )

        if not expected_pdbqt.is_file():
            raise ReceptorPrepError(
                member_id=member_id,
                returncode=completed.returncode,
                stderr=(
                    f"mk_prepare_receptor.py exited 0 but expected output file "
                    f"{expected_pdbqt} was not created."
                ),
            )

        return EnsembleMemberPrepResult(
            member_id=member_id,
            success=True,
            receptor_pdbqt_path=expected_pdbqt,
            params=params,
            dropped_residues=dropped_residues,
        )

    except (ResidueTemplateError, ReceptorPrepError, Exception) as exc:
        return EnsembleMemberPrepResult(
            member_id=member_id,
            success=False,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )


def _prepare_ensemble_batch(
    ensemble_path: Path | str,
    output: Path | str,
    params: EnsemblePrepParams,
    n_workers: int | None = None,
) -> EnsemblePrepResults:
    n_workers = n_workers or os.cpu_count()
    ensemble_path = Path(ensemble_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    ensemble: Ensemble = load_ensemble(ensemble_path)
    results: list[EnsembleMemberPrepResult] = []

    for _cs in ensemble.manifest.conformational_states:
        result = _prepare_structure(
            root_path=ensemble_path,
            conformational_state=_cs,
            output=output,
            params=params,
        )
        results.append(result)

    return EnsemblePrepResults(
        ensemble_id=ensemble.manifest.id,
        ensemble_content_hash=ensemble.manifest.content_hash,
        results=results,
    )


def _parse_num_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--ensemble-path",
        type=Path,
        help="Protein conformational ensemble package directory.",
    )
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for combined raw BindingSite JSON list",
    )
    p.add_argument(
        "--workers",
        type=_parse_num_workers,
        default="auto",
        help="Number of parallel p2rank workers, or 'auto' for os.cpu_count()",
    )
    return p.parse_args()


def prepare_ensemble():
    args = _parse_args()
    _prepare_ensemble_batch(
        args.ensemble_path, args.output, EnsemblePrepParams(), args.workers
    )
