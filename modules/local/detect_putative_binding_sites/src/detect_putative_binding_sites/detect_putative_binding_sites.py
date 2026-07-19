# modules/local/surface_extract/src/detect_putative_binding_sites/detect_putative_binding_sites.py


import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from lynceus_chem.models.binding_site import BindingSite, Sphere
from pce.ensemble import Ensemble, load_ensemble
from pce.models import (
    ConformationalState,
    MultiModelStructure,
    StandaloneStructure,
    Structure,
    TrajectoryStructure,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# fpocket output file naming conventions (fpocket 4.x): given input
# structure.cif, `fpocket -f structure.cif` writes a sibling directory
# structure_out/, with structure_out/<name>_info.txt summarizing all
# pockets and structure_out/pockets/pocket{N}_atm.cif per pocket.
# fpocket dispatches its parser by file extension, so inputs and its
# own pocket outputs stay in the same format (mmCIF here, matching
# Lynceus's structure file convention).
_POCKET_HEADER_RE = re.compile(r"^Pocket\s+(\d+)\s*:?\s*$")
_POCKET_SCORE_RE = re.compile(r"^\s*Score\s*:\s*([-\d.]+)\s*$")


def _uri_to_path(uri: str, ensemble_root: Path) -> Path:
    """Resolve a manifest `uri` to a local filesystem path.

    Per `pce.package.load_ensemble`, `Ensemble.root` is the package
    directory and manifest `uri` fields are relative to it (the loader
    never rewrites them to absolute paths). `file://` uris and already-
    absolute paths are passed through as-is.
    """
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
            "trajectory-backed structures are not yet supported for fpocket "
            "detection; frame extraction to a standalone structure file is "
            "unimplemented"
        )

    raise TypeError(f"unrecognized structure type: {type(structure).__name__}")


def _run_fpocket(local_input: Path) -> Path:
    subprocess.run(
        ["fpocket", "-f", str(local_input)],
        check=True,
        capture_output=True,
        text=True,
    )

    out_dir = local_input.parent / f"{local_input.stem}_out"
    if not out_dir.is_dir():
        raise RuntimeError(f"fpocket did not produce expected output dir: {out_dir}")
    return out_dir


def _parse_pocket_scores(info_file: Path) -> dict[int, float]:
    scores: dict[int, float] = {}
    current_pocket: int | None = None

    with open(info_file) as _f:
        for line in _f:
            header_match = _POCKET_HEADER_RE.match(line)
            if header_match:
                current_pocket = int(header_match.group(1))
                continue
            score_match = _POCKET_SCORE_RE.match(line)
            if score_match and current_pocket is not None:
                scores[current_pocket] = float(score_match.group(1))

    return scores


def _parse_atom_site_coords(cif_path: Path) -> list[tuple[float, float, float]]:
    lines = Path(cif_path).read_text().splitlines()

    columns: list[str] = []
    in_atom_site_loop = False
    data_start: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "loop_":
            in_atom_site_loop = False
            columns = []
            continue
        if stripped.startswith("_atom_site."):
            in_atom_site_loop = True
            columns.append(stripped[len("_atom_site.") :])
            continue
        if in_atom_site_loop and columns and not stripped.startswith("_"):
            data_start = i
            break

    if data_start is None:
        return []

    x_idx = columns.index("Cartn_x")
    y_idx = columns.index("Cartn_y")
    z_idx = columns.index("Cartn_z")

    points: list[tuple[float, float, float]] = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "_", "loop_")):
            break
        fields = stripped.split()
        if len(fields) <= max(x_idx, y_idx, z_idx):
            continue
        points.append(
            (float(fields[x_idx]), float(fields[y_idx]), float(fields[z_idx]))
        )

    return points


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    n = len(points)
    sx = sum(p[0] for p in points) / n
    sy = sum(p[1] for p in points) / n
    sz = sum(p[2] for p in points) / n
    return (sx, sy, sz)


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


def _pockets_to_binding_sites(
    out_dir: Path, conformational_state_id: str
) -> list[BindingSite]:
    info_files = list(out_dir.glob("*_info.txt"))
    if not info_files:
        logger.warning("no fpocket info file found in %s", out_dir)
        return []

    scores = _parse_pocket_scores(info_files[0])
    pocket_cifs = sorted((out_dir / "pockets").glob("pocket*_atm.cif"))

    binding_sites: list[BindingSite] = []

    for pocket_cif in pocket_cifs:
        pocket_num_match = re.search(r"pocket(\d+)_atm\.cif", pocket_cif.name)
        if not pocket_num_match:
            continue
        pocket_num = int(pocket_num_match.group(1))

        points = _parse_atom_site_coords(pocket_cif)
        if not points:
            continue

        center = _centroid(points)
        radius = _radius_of_gyration(points, center)

        binding_sites.append(
            BindingSite(
                schema_version="1.0.0",
                site_id=f"{conformational_state_id}:fpocket:{pocket_num}",
                conformational_state_id=conformational_state_id,
                center=center,
                extent=Sphere(center=center, radius=radius),
                pocket_score=scores.get(pocket_num),
                provenance={"tool": "fpocket", "pocket_index": pocket_num},
            )
        )

    return binding_sites


def _detect_putative_binding_sites(
    conformational_state: ConformationalState, ensemble_root: Path
) -> list[BindingSite]:
    logger.info(
        "detecting putative sites for conformational state: %s",
        conformational_state.id,
    )

    with tempfile.TemporaryDirectory(prefix="fpocket_") as _tmp:
        workdir = Path(_tmp)
        local_input = _structure_to_local_cif(
            conformational_state.structure, ensemble_root, workdir
        )
        out_dir = _run_fpocket(local_input)
        return _pockets_to_binding_sites(out_dir, conformational_state.id)


def _detect_putative_binding_sites_ensemble(
    ensemble_path: Path, num_workers: int
) -> list[BindingSite]:
    ensemble: Ensemble = load_ensemble(ensemble_path)
    conformational_states = list(ensemble.manifest.conformational_states)

    binding_sites: list[BindingSite] = []

    with ProcessPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(_detect_putative_binding_sites, _c, ensemble.root): _c
            for _c in conformational_states
        }
        for future in as_completed(futures):
            conformational_state = futures[future]
            try:
                binding_sites.extend(future.result())
            except Exception:
                logger.exception(
                    "fpocket detection failed for conformational state: %s",
                    conformational_state.id,
                )
                raise

    return binding_sites


def _write_putative_binding_sites(
    putative_binding_sites: list[BindingSite], output_file: Path
):
    with open(output_file, "w") as _f:
        json.dump([_b.to_dict() for _b in putative_binding_sites], _f)


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
        "--ensemble",
        type=Path,
        help="Protein conformational ensemble package directory (contains manifest.yaml)",
    )
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for combined raw BindingSite JSON list",
    )
    p.add_argument(
        "--workers",
        type=_parse_num_workers,
        default="auto",
        help="Number of parallel fpocket workers, or 'auto' for os.cpu_count()",
    )
    return p.parse_args()


def detect_putative_binding_sites():
    args = _parse_args()
    putative_binding_sites: list[BindingSite] = _detect_putative_binding_sites_ensemble(
        args.ensemble, args.workers
    )

    _write_putative_binding_sites(putative_binding_sites, args.out)
