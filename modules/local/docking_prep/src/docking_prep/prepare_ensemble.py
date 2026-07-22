# modules/local/docking_prep/docking-prep/src/docking_prep/prepare_ensemble.py

import argparse
import logging
import os
from pathlib import Path
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


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
        help="Number of parallel p2rank workers, or 'auto' for os.cpu_count()",
    )
    return p.parse_args()


def docking_prep_ensemble():
    args = _parse_args()
    logger.info(
        "docking_prep_ensemble for: %s",
    )
