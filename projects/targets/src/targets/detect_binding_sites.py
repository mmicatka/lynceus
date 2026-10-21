# projects/targets/src/targets/detect_binding_sites.py

import csv
import json
import os
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click
import gemmi
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import get_lynceus_logger, wide_log
from protein_ensemble import Manifest

from targets.models import BindingSite, EnsembleBindingSites, Sphere

logger = get_lynceus_logger()

MANIFEST_FILENAME = "manifest.json"

# Exact header written by p2rank's PredictionSummary.toCSV()
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


def _load_manifest(ensemble_path: Path) -> Manifest:
    manifest_file = ensemble_path / MANIFEST_FILENAME
    if not manifest_file.is_file():
        raise RuntimeError(f"Manifest not found at {manifest_file}")
    return Manifest.load(ensemble_path)


def _marker_path(output_path: str) -> str:
    return f"{output_path}.SUCCESS"


def _is_valid(output_path: str, num_members: int) -> bool:
    marker_path = _marker_path(output_path)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_members") == num_members


def _write_success_marker(output_path: str, num_members: int) -> None:
    with open(_marker_path(output_path), "w") as f:
        json.dump({"num_members": num_members}, f)


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
                f"columns {sorted(missing)}; found columns {fieldnames}."
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
        break

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
    member_id: str,
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
            "pocket rank surf_atom_ids not found in structure; "
            "radius computed from resolved atoms only",
            pocket_rank=pocket_rank,
            member_id=member_id,
            missing_count=missing_count,
            total_atoms=len(surf_atom_ids),
        )

    if not points:
        logger.warning(
            "no surf_atom_ids resolved to structure coordinates;"
            " skipping (cannot compute radius)",
            pocket_rank=pocket_rank,
            member_id=member_id,
        )
        return None

    radius = _radius_of_gyration(points, center)

    return BindingSite(
        schema_version="1.0.0",
        site_id=f"{member_id}:p2rank:{pocket_rank}",
        member_id=member_id,
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
    member_id: str,
) -> list[BindingSite]:
    rows = _parse_predictions_csv(predictions_csv)
    if not rows:
        logger.warning(
            "p2rank produced no predicted pockets",
            member_id=member_id,
        )
        return []

    coords_by_serial = _resolve_atom_coords(structure_path)
    binding_sites: list[BindingSite] = []

    for row in rows:
        binding_site = _pocket_row_to_binding_site(row, member_id, coords_by_serial)
        if binding_site is not None:
            binding_sites.append(binding_site)

    return binding_sites


def _detect_binding_sites(
    manifest: Manifest, member_id: str, ensemble_path: Path
) -> list[BindingSite]:
    logger.info("Detecting sites for member", member_id=member_id)

    source_path = Path(manifest.structure_path(member_id))
    local_input = ensemble_path / "members" / source_path.name

    if not local_input.is_file():
        raise RuntimeError(f"Structure file not found: {local_input}")

    with tempfile.TemporaryDirectory(prefix="p2rank_") as _tmp:
        workdir = Path(_tmp)
        predictions_csv = _run_p2rank(local_input, workdir)
        return _pockets_to_binding_sites(predictions_csv, local_input, member_id)


def _detect_binding_sites_ensemble(
    manifest: Manifest, ensemble_path: Path, num_workers: int
) -> list[BindingSite]:
    binding_sites: list[BindingSite] = []

    with ProcessPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(
                _detect_binding_sites, manifest, _member_id, ensemble_path
            ): _member_id
            for _member_id in manifest.members
        }

        for future in as_completed(futures):
            member_id = futures[future]
            try:
                binding_sites.extend(future.result())
            except Exception:
                logger.exception(
                    "p2rank detection failed for member",
                    member_id=member_id,
                )
                raise

    return binding_sites


def _get_all_binding_sites(
    output_path: str,
    ensemble_dir: Path,
    manifest: Manifest,
    num_workers: int,
) -> list[BindingSite]:
    num_members = len(list(manifest.members))

    if _is_valid(output_path, num_members):
        logger.info(
            "Binding sites already detected, loading from disk to apply filtering.",
            ensemble_path=str(ensemble_dir),
            output_path=output_path,
            num_members=num_members,
        )
        with open(output_path, "r") as f:
            raw_data = json.load(f)
            return [BindingSite(**site) for site in raw_data]

    logger.info(
        "Detecting binding sites for ensemble",
        ensemble_path=str(ensemble_dir),
        num_members=num_members,
        output_path=output_path,
        workers=num_workers,
    )

    binding_sites = _detect_binding_sites_ensemble(manifest, ensemble_dir, num_workers)

    binding_sites_dicts = [_b.to_dict() for _b in binding_sites]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as _f:
        json.dump(binding_sites_dicts, _f)

    _write_success_marker(output_path, num_members)

    return binding_sites


def _filter_binding_sites(
    all_sites: list[BindingSite],
    ensemble_id: str,
    min_pocket_score: float,
) -> EnsembleBindingSites:

    filtered_sites = [
        site
        for site in all_sites
        if site.pocket_score is not None and site.pocket_score >= min_pocket_score
    ]

    return EnsembleBindingSites(ensemble_id=ensemble_id, binding_sites=filtered_sites)


@click.command("detect_binding_sites")
@click.option(
    "--ensemble",
    "ensemble_path",
    required=True,
    type=str,
    help="Path to the input ensemble folder.",
)
@click.option(
    "--ensemble-id",
    "ensemble_id",
    type=str,
    default=None,
    help="Ensemble identifier. Defaults to the ensemble folder name.",
)
@click.option(
    "--min-pocket-score",
    "min_pocket_score",
    required=True,
    type=float,
    help="Minimum pocket score required to retain a binding site.",
)
@click.option(
    "--num-workers",
    "num_workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def detect_binding_sites(
    ensemble_path: str,
    ensemble_id: str | None,
    min_pocket_score: float,
    num_workers: int,
):
    click.echo(f"Processing ensemble at {ensemble_path}...")

    ensemble_dir = Path(ensemble_path)
    ensemble_id = ensemble_id or ensemble_dir.name
    manifest = _load_manifest(ensemble_dir)

    output_path = str(ensemble_dir / "binding_sites" / "binding_sites.json")
    filtered_output_path = str(
        ensemble_dir / "binding_sites" / "binding_sites_filtered.json"
    )

    all_sites = _get_all_binding_sites(
        output_path=output_path,
        ensemble_dir=ensemble_dir,
        manifest=manifest,
        num_workers=num_workers,
    )

    selected = _filter_binding_sites(
        all_sites=all_sites,
        ensemble_id=ensemble_id,
        min_pocket_score=min_pocket_score,
    )

    if not selected:
        raise click.ClickException(
            f"no binding sites in ensemble '{ensemble_id}' have "
            f"pocket_score >= {min_pocket_score}"
        )

    os.makedirs(os.path.dirname(filtered_output_path), exist_ok=True)
    with open(filtered_output_path, "w") as _f:
        json.dump(selected.to_dict(), _f)

    logger.info(
        "Finished detecting and filtering binding sites", ensemble_path=ensemble_path
    )
    click.echo("Done!")
