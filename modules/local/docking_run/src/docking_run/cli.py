# modules/local/docking_run/src/docking_run/docking_run.py

import argparse
import logging
import sys
from pathlib import Path

from .providers import available_providers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Generate ranked, deduplicated multi-conformer PDBQT sets per "
            "candidate from a Parquet file of SMILES, packaged as an LMDB "
            "keyed by candidate id."
        )
    )
    p.add_argument(
        "--provider",
        choices=available_providers(),
        required=True,
        help="Docking backend to use.",
    )
    p.add_argument(
        "--receptor",
        type=Path,
        required=True,
        help="Receptor structure in PDBQT format.",
    )
    p.add_argument(
        "--ligands",
        type=Path,
        nargs="+",
        required=True,
        help="One or more ligand PDBQT files to dock against the receptor.",
    )
    p.add_argument(
        "--center",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        required=True,
        help="Search box center, Angstroms.",
    )
    p.add_argument(
        "--size",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        required=True,
        help="Search box size, Angstroms.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=(
            "Max ligands per underlying provider invocation. CPU provider "
            "ignores this (no native batch primitive; see VinaCPUProvider "
            "docstring). GPU provider chunks --ligands into groups of at "
            "most this size per Vina-GPU+ invocation. Defaults to the "
            "selected provider's own default."
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Directory for provider output files. "
            "Defaults to a provider-specific ./vina_{provider}_out.",
        ),
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="If set, write docking results as JSON.",
    )

    cpu_group = p.add_argument_group("CPU provider options")
    cpu_group.add_argument(
        "--exhaustiveness",
        type=int,
        default=8,
        help="[cpu] Vina search exhaustiveness..",
    )
    cpu_group.add_argument(
        "--n-poses",
        type=int,
        default=9,
        help="[cpu] Number of output poses per ligand.",
    )
    cpu_group.add_argument(
        "--n-workers",
        type=int,
        default=1,
        help="[cpu] Number of worker processes for dock_batch (1 = sequential).",
    )

    gpu_group = p.add_argument_group("GPU provider options")
    gpu_group.add_argument(
        "--vina-gpu-binary",
        type=str,
        default=None,
        help="[gpu] Path to the Vina-GPU+ binary. Defaults to 'Vina-GPU+'.",
    )
    gpu_group.add_argument(
        "--search-depth",
        type=int,
        default=None,
        help="[gpu] Vina-GPU+ search depth. Defaults to the binary's own heuristic.",
    )
    gpu_group.add_argument(
        "--thread",
        type=int,
        default=1000,
        help="[gpu] Vina-GPU+ docking-lane parallelism (--thread). Keep below 10000.",
    )

    return p.parse_args()


def docking_run():
    args = _parse_args()
