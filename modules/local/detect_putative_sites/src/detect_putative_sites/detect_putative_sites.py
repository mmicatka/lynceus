# modules/local/surface_extract/src/detect_putative_sites/detect_putative_sites.py

import argparse
import json
import logging
import os
from pathlib import Path
import sys

from pce.ensemble import Ensemble, load_ensemble
from chem.binding_site import BindingSite
from pce.models import ConformationalState


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _detect_putative_sites(
    conformational_state: ConformationalState,
) -> list[BindingSite]:
    logger.info(
        "detecting putative sites for conformational state: %s", conformational_state.id
    )

    return []


def _detect_putative_sites_ensemble(ensemble_path: Path) -> list[BindingSite]:
    ensemble: Ensemble = load_ensemble(ensemble_path)

    binding_sites: list[BindingSite] = []

    for _c in ensemble.manifest.conformational_states:
        binding_sites.append(_detect_putative_sites(_c))

    return binding_sites


def _write_putative_binding_sites(
    putative_binding_sites: list[BindingSite], output_file: Path
):
    with open(output_file, "w") as _f:
        json.dump(putative_binding_sites, _f)


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
    return p.parse_args()


def _main():
    args = _parse_args()
    putative_binding_sites: list[BindingSite] = _detect_putative_sites_ensemble(
        args.ensemble
    )

    _write_putative_binding_sites(putative_binding_sites, args.out)


if __name__ == "__main__":
    _main()
