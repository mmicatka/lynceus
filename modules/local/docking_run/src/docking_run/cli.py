# modules/local/docking_run/src/docking_run/docking_run.py

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .providers import ProviderNotAvailableError, available_providers, get_provider
from .types import DockingError, SearchBox
from .types.docking_result import DockingResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _build_provider_kwargs(args: argparse.Namespace) -> dict:
    common = {"out_dir": args.out_dir} if args.out_dir else {}
    if args.provider == "cpu":
        return {
            **common,
            "exhaustiveness": args.exhaustiveness,
            "n_poses": args.n_poses,
            "n_workers": args.n_workers,
        }
    if args.provider == "gpu":
        return {
            **common,
            "binary_path": args.vina_gpu_binary,
            "search_depth": args.search_depth,
            "thread": args.thread,
        }
    # Should be unreachable: argparse `choices=` already restricts this.
    raise ValueError(f"Unhandled provider: {args.provider}")


def _results_to_json(results_by_ligand: dict[str, list[DockingResult]]) -> str:
    serializable = {
        ligand_id: [
            {
                "mode": r.mode,
                "affinity_kcal_mol": r.affinity_kcal_mol,
                "rmsd_lb": r.rmsd_lb,
                "rmsd_ub": r.rmsd_ub,
                "pose_pdbqt": str(r.pose_pdbqt),
            }
            for r in results
        ]
        for ligand_id, results in results_by_ligand.items()
    }
    return json.dumps(serializable, indent=2)


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

    provider_kwargs = _build_provider_kwargs(args)
    provider = get_provider(args.provider, **provider_kwargs)

    try:
        provider.validate_environment()
    except ProviderNotAvailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    box = SearchBox(center=tuple(args.center), size=tuple(args.size))

    try:
        results_by_ligand = provider.dock_batch(
            receptor_pdbqt=args.receptor,
            ligand_pdbqts=list(args.ligands),
            box=box,
            batch_size=args.batch_size,
        )
    except DockingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = _results_to_json(results_by_ligand)
    print(output)
    if args.out_json:
        args.out_json.write_text(output)
