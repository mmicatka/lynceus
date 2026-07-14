# modules/local/surface_extract/src/detect_putative_sites/detect_putative_sites.py

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


def _detect_putative_sites() -> list[BindingSite]:
    pass


def _parse_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "pce_dir",
        type=Path,
        help="Protein conformational ensemble package directory (contains manifest.yaml)",
    )
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for combined raw BindingSite JSON list",
    )
    p.add_argument("--workers", metavar="N|auto", default="auto", type=_parse_workers)
    return p.parse_args()


def _main():
    args = _parse_args()
    _detect_putative_sites()


if __name__ == "__main__":
    _main()
