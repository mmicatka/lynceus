# modules/local/detect_binding_sites/src/detect_binding_sites/detect_binding_sites.py
import csv
import json
import logging
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import click
import gemmi
from lynceus_utils.cli import NumWorkers
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
from protein_ensemble import Manifest

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


def _member_to_local_cif(
    manifest: Manifest, member_id: str, workdir: Path, fs, ensemble_uri: str
) -> Path:
    source_path = Path(manifest.structure_path(member_id))
    local_path = (workdir / source_path.name).with_suffix(".cif")

    remote_path = f"{ensemble_uri}/members/{source_path.name}"
    fs.get(remote_path, str(local_path))

    return local_path


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
        # _member_to_local_cif before p2rank ever sees them.

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
            "pocket rank %s (%s): %d/%d surf_atom_ids not found in structure; "
            "radius computed from the %d resolved atoms only",
            pocket_rank,
            member_id,
            missing_count,
            len(surf_atom_ids),
            len(points),
        )

    if not points:
        logger.warning(
            "pocket rank %s (%s): no surf_atom_ids resolved to structure "
            "coordinates; skipping (cannot compute a radius)",
            pocket_rank,
            member_id,
        )
        return None

    # Radius of gyration about p2rank's own reported pocket center
    radius = _radius_of_gyration(points, center)

    return BindingSite(
        schema_version="1.0.0",
        site_id=f"{member_id}:p2rank:{pocket_rank}",
        conformational_state_id=member_id,
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
            "p2rank produced no predicted pockets for member: %s",
            member_id,
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
    manifest: Manifest, member_id: str, ensemble_uri: str, bucket: Optional[str]
) -> list[BindingSite]:
    logger.info("detecting sites for member: %s", member_id)

    blob_storage_settings = get_blob_storage_settings() if bucket else None
    fs = get_filesystem(blob_storage_settings)

    with tempfile.TemporaryDirectory(prefix="p2rank_") as _tmp:
        workdir = Path(_tmp)
        local_input = _member_to_local_cif(
            manifest, member_id, workdir, fs, ensemble_uri
        )
        predictions_csv = _run_p2rank(local_input, workdir)
        return _pockets_to_binding_sites(predictions_csv, local_input, member_id)


def _detect_binding_sites_ensemble(
    ensemble_uri: str, num_workers: int, bucket: Optional[str], fs
) -> list[BindingSite]:
    manifest_uri = f"{ensemble_uri}/manifest.json"

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_manifest_path = Path(tmp_dir) / "manifest.json"
        fs.get(manifest_uri, str(local_manifest_path))
        manifest = Manifest.load(str(local_manifest_path))

    member_ids = list(manifest.members)
    binding_sites: list[BindingSite] = []

    with ProcessPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(
                _detect_binding_sites, manifest, _member_id, ensemble_uri, bucket
            ): _member_id
            for _member_id in member_ids
        }

        for future in as_completed(futures):
            member_id = futures[future]
            try:
                binding_sites.extend(future.result())
            except Exception:
                logger.exception(
                    "p2rank detection failed for member: %s",
                    member_id,
                )
                raise

    return binding_sites


def _write_binding_sites(binding_sites: list[BindingSite], output_uri: str, fs):
    with fs.open(output_uri, "w") as _f:
        json.dump([_b.to_dict() for _b in binding_sites], _f)


@click.command()
@click.option("--ensemble", type=str, required=True, help="Path to the input ensemble.")
@click.option("--out", type=str, required=True, help="Path to the output JSON file.")
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def detect_binding_sites(
    ensemble: str,
    out: str,
    bucket: str,
    num_workers: int,
):
    logger.info("detecting binding sites for %s", ensemble)

    blob_storage_settings = get_blob_storage_settings() if bucket else None
    fs = get_filesystem(blob_storage_settings)

    ensemble_uri = f"s3://{bucket}/{ensemble}" if bucket else ensemble
    out_uri = f"s3://{bucket}/{out}" if bucket else out

    binding_sites = _detect_binding_sites_ensemble(
        ensemble_uri, num_workers, bucket, fs
    )

    _write_binding_sites(binding_sites, out_uri, fs)
