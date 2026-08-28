# modules/local/detect_binding_sites/src/detect_binding_sites/detect_binding_sites.py

import argparse
import csv
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click
import gemmi
from pce.ensemble import Ensemble, load_ensemble
from pce.models import (
    ConformationalState,
    MultiModelStructure,
    StandaloneStructure,
    Structure,
    TrajectoryStructure,
)

from .models import BindingSite, Sphere

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Exact header written by p2rank's PredictionSummary.toCSV() (PredictionSummary.groovy,
# rdk/p2rank, as of v2.6 / develop branch). Verified against source rather than assumed,
# since a silently-wrong column name here would fail parsing without a clear signal.
_P2RANK_PREDICTIONS_HEADER = (
    "name",
    "rank",
    "score",
    "probability",
    "sas_points",
    "surf_atoms",
    "center_x",
    "center_y",
    "center_z",
    "residue_ids",
    "surf_atom_ids",
)


def _uri_to_path(uri: str, ensemble_root: Path) -> Path:
    if uri.startswith("file://"):
        return Path(uri[len("file://") :])
    path = Path(uri)
    return path if path.is_absolute() else ensemble_root / path


def _structure_to_local_cif(
    structure: Structure, ensemble_root: Path, workdir: Path
) -> Path:
    if isinstance(structure, (StandaloneStructure, MultiModelStructure)):
        source_path = _uri_to_path(structure.uri, ensemble_root)
        local_path = (workdir / source_path.name).with_suffix(".cif")
        shutil.copy(source_path, local_path)
        return local_path

    if isinstance(structure, TrajectoryStructure):
        raise NotImplementedError(
            "trajectory-backed structures are not yet supported for p2rank "
            "detection; frame extraction to a standalone structure file is "
            "unimplemented"
        )

    raise TypeError(f"unrecognized structure type: {type(structure).__name__}")


def _run_p2rank(local_input: Path, workdir: Path) -> Path:
    out_dir = workdir / "p2rank_out"

    subprocess.run(
        ["prank", "predict", "-f", str(local_input), "-o", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
    )

    predictions_csv = out_dir / f"{local_input.name}_predictions.csv"
    if not predictions_csv.is_file():
        raise RuntimeError(
            f"p2rank did not produce expected predictions file: {predictions_csv}"
        )
    return predictions_csv


def _parse_predictions_csv(predictions_csv: Path) -> list[dict[str, str]]:
    with open(predictions_csv, newline="") as _f:
        reader = csv.DictReader(_f, skipinitialspace=True)
        fieldnames = tuple(_f_name.strip() for _f_name in (reader.fieldnames or ()))

        missing = set(_P2RANK_PREDICTIONS_HEADER) - set(fieldnames)
        if missing:
            raise RuntimeError(
                f"p2rank predictions CSV {predictions_csv} is missing expected "
                f"columns {sorted(missing)}; found columns {fieldnames}. "
                "This likely means the installed p2rank version's output "
                "format has changed and this parser needs updating."
            )

        return [{_k.strip(): _v.strip() for _k, _v in row.items()} for row in reader]


def _resolve_atom_coords(structure_path: Path) -> dict[int, tuple[float, float, float]]:
    parsed = gemmi.read_structure(str(structure_path))

    coords_by_serial: dict[int, tuple[float, float, float]] = {}
    for model in parsed:
        for chain in model:
            for residue in chain:
                for atom in residue:
                    coords_by_serial[atom.serial] = (
                        atom.pos.x,
                        atom.pos.y,
                        atom.pos.z,
                    )
        break  # only the first model is relevant; standalone/multi-model
        # structures are already reduced to a single conformation by
        # _structure_to_local_cif before p2rank ever sees them.

    return coords_by_serial


def _radius_of_gyration(
    points: list[tuple[float, float, float]], center: tuple[float, float, float]
) -> float:
    n = len(points)
    return (
        sum(
            (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2 + (p[2] - center[2]) ** 2
            for p in points
        )
        / n
    ) ** 0.5


def _pocket_row_to_binding_site(
    row: dict[str, str],
    conformational_state_id: str,
    coords_by_serial: dict[int, tuple[float, float, float]],
) -> BindingSite | None:
    pocket_rank = row["rank"]
    center = (
        float(row["center_x"]),
        float(row["center_y"]),
        float(row["center_z"]),
    )

    surf_atom_ids = [int(_s) for _s in row["surf_atom_ids"].split()]
    points = [
        coords_by_serial[_serial]
        for _serial in surf_atom_ids
        if _serial in coords_by_serial
    ]

    missing_count = len(surf_atom_ids) - len(points)
    if missing_count:
        logger.warning(
            "pocket rank %s (%s): %d/%d surf_atom_ids not found in structure; "
            "radius computed from the %d resolved atoms only",
            pocket_rank,
            conformational_state_id,
            missing_count,
            len(surf_atom_ids),
            len(points),
        )

    if not points:
        logger.warning(
            "pocket rank %s (%s): no surf_atom_ids resolved to structure "
            "coordinates; skipping (cannot compute a radius)",
            pocket_rank,
            conformational_state_id,
        )
        return None

    # Radius of gyration about p2rank's own reported pocket center (a centroid
    # of SAS points, not of surf_atom_ids), for consistency with the fpocket
    # path this replaces, which also derives radius from real pocket geometry
    # rather than a fixed/configurable constant.
    radius = _radius_of_gyration(points, center)

    return BindingSite(
        schema_version="1.0.0",
        site_id=f"{conformational_state_id}:p2rank:{pocket_rank}",
        conformational_state_id=conformational_state_id,
        center=center,
        extent=Sphere(center=center, radius=radius),
        pocket_score=float(row["score"]),
        provenance={
            "tool": "p2rank",
            "pocket_rank": int(pocket_rank),
            "probability": float(row["probability"]),
        },
    )


def _pockets_to_binding_sites(
    predictions_csv: Path,
    structure_path: Path,
    conformational_state_id: str,
) -> list[BindingSite]:
    rows = _parse_predictions_csv(predictions_csv)
    if not rows:
        logger.warning(
            "p2rank produced no predicted pockets for conformational state: %s",
            conformational_state_id,
        )
        return []

    coords_by_serial = _resolve_atom_coords(structure_path)

    binding_sites: list[BindingSite] = []
    for row in rows:
        binding_site = _pocket_row_to_binding_site(
            row, conformational_state_id, coords_by_serial
        )
        if binding_site is not None:
            binding_sites.append(binding_site)

    return binding_sites


def _detect_binding_sites(
    conformational_state: ConformationalState, ensemble_root: Path
) -> list[BindingSite]:
    logger.info(
        "detecting sites for conformational state: %s",
        conformational_state.id,
    )

    with tempfile.TemporaryDirectory(prefix="p2rank_") as _tmp:
        workdir = Path(_tmp)
        local_input = _structure_to_local_cif(
            conformational_state.structure, ensemble_root, workdir
        )
        predictions_csv = _run_p2rank(local_input, workdir)
        return _pockets_to_binding_sites(
            predictions_csv, local_input, conformational_state.id
        )


def _detect_binding_sites_ensemble(
    ensemble_path: Path, num_workers: int
) -> list[BindingSite]:
    ensemble: Ensemble = load_ensemble(ensemble_path)
    conformational_states = list(ensemble.manifest.conformational_states)

    binding_sites: list[BindingSite] = []

    with ProcessPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(_detect_binding_sites, _c, ensemble.root): _c
            for _c in conformational_states
        }
        for future in as_completed(futures):
            conformational_state = futures[future]
            try:
                binding_sites.extend(future.result())
            except Exception:
                logger.exception(
                    "p2rank detection failed for conformational state: %s",
                    conformational_state.id,
                )
                raise

    return binding_sites


def _write_binding_sites(binding_sites: list[BindingSite], output_file: Path):
    with open(output_file, "w") as _f:
        json.dump([_b.to_dict() for _b in binding_sites], _f)


def _parse_num_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


@click.command(help=__doc__)
@click.option(
    "--ensemble",
    type=click.Path(exists=True, path_type=Path),
    help="Protein conformational ensemble package directory.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="Output path for combined raw BindingSite JSON list.",
)
@click.option(
    "--workers",
    default="auto",
    show_default=True,
    type=_parse_num_workers,
    help="Number of parallel p2rank workers, or 'auto' for os.cpu_count()",
)
def detect_binding_sites(ensemble: Path | None, out: Path, workers: int | str):
    putative_binding_sites: list[BindingSite] = _detect_binding_sites_ensemble(
        ensemble, workers
    )
    _write_binding_sites(putative_binding_sites, out)
