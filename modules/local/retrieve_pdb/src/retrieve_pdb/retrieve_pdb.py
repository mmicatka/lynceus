# modules/local/retrieve_pdb/src/retrieve_pdb.py

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

_RCSB_CIF_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.cif"
_RCSB_PDB_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.pdb"

_MAX_TRIES = 3
_RETRY_WAIT_SECONDS = 2
_TIMEOUT_SECONDS = 30.0


def _fetch(client: httpx.Client, url: str) -> bytes | None:
    for attempt in range(1, _MAX_TRIES + 1):
        try:
            response = client.get(url, timeout=_TIMEOUT_SECONDS)
            if response.status_code == 200 and response.content:
                return response.content
        except httpx.HTTPError:
            pass

        if attempt < _MAX_TRIES:
            time.sleep(_RETRY_WAIT_SECONDS)

    return None


def download_structures(pdb_ids: list[str], outdir: Path) -> dict[str, Path]:
    normalized = [p.strip().upper() for p in pdb_ids]
    outdir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}
    failures: list[str] = []

    with httpx.Client(follow_redirects=True) as client:
        for pdb_id in normalized:
            cif_content = _fetch(client, _RCSB_CIF_TEMPLATE.format(pdb_id=pdb_id))
            if cif_content is not None:
                path = outdir / f"{pdb_id}.cif"
                path.write_bytes(cif_content)
                results[pdb_id] = path
                continue

            pdb_content = _fetch(client, _RCSB_PDB_TEMPLATE.format(pdb_id=pdb_id))
            if pdb_content is not None:
                path = outdir / f"{pdb_id}.pdb"
                path.write_bytes(pdb_content)
                results[pdb_id] = path
                continue

            failures.append(pdb_id)

    if failures:
        msg = (
            f"Failed to download structures for {failures} as .cif or .pdb "
            f"from RCSB (requested: {normalized})"
        )
        raise RuntimeError(msg)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download structure files for a list of PDB IDs, serially, via httpx."
    )
    parser.add_argument(
        "--pdb-ids",
        type=str,
        required=True,
        help="Comma-separated list of PDB IDs, e.g. '1STP' or '1STP,3PTB'.",
    )
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    pdb_ids = [p.strip() for p in args.pdb_ids.split(",") if p.strip()]
    if not pdb_ids:
        print("FATAL: --pdb-ids resolved to an empty list", file=sys.stderr)
        raise SystemExit(1)

    try:
        results = download_structures(pdb_ids, args.outdir)
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for pdb_id, path in results.items():
        print(f"Downloaded {pdb_id} -> {path}")


if __name__ == "__main__":
    main()
