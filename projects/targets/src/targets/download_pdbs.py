# projects/targets/src/targets/download_target.py

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click
import httpx
import structlog
from lynceus_core.logging import wide_log

_RCSB_CIF_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.cif"
_RCSB_PDB_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.pdb"

_MAX_TRIES = 3
_RETRY_WAIT_SECONDS = 2
_TIMEOUT_SECONDS = 30.0


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger(__name__)


def _marker_path(outdir: Path) -> Path:
    return outdir / "_SUCCESS_download_pdbs.json"


def _is_valid(outdir: Path, pdb_ids: list[str]) -> bool:
    marker_path = _marker_path(outdir)
    if not marker_path.exists():
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("pdb_ids") == sorted(pdb_ids)


def _write_success_marker(outdir: Path, pdb_ids: list[str]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    with open(_marker_path(outdir), "w") as f:
        json.dump({"pdb_ids": sorted(pdb_ids)}, f)


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


@click.command("download_pdbs")
@click.option(
    "--pdb-ids",
    "pdb_ids_str",
    required=True,
    type=str,
    help="Comma-separated list of PDB IDs, e.g. '1STP' or '1STP,3PTB'.",
)
@click.option(
    "--outdir",
    "outdir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for downloaded structures.",
)
@wide_log(logger)
def download_pdbs(pdb_ids_str: str, outdir: Path) -> None:
    pdb_ids = [p.strip().upper() for p in pdb_ids_str.split(",") if p.strip()]
    if not pdb_ids:
        click.echo("FATAL: --pdb-ids resolved to an empty list", err=True)
        raise SystemExit(1)

    click.echo(f"Processing {len(pdb_ids)} PDB IDs...")

    if _is_valid(outdir, pdb_ids):
        logger.info(
            "Target state already achieved, skipping downloads",
            outdir=str(outdir),
            num_pdbs=len(pdb_ids),
        )
        click.echo("Done!")
        return

    logger.info("Retrieving structures", outdir=str(outdir), num_pdbs=len(pdb_ids))

    try:
        results = download_structures(pdb_ids, outdir)
    except RuntimeError as exc:
        logger.error("Failed to download structures", error=str(exc))
        click.echo(f"FATAL: {exc}", err=True)
        raise SystemExit(1) from exc

    for pdb_id, path in results.items():
        logger.info("Downloaded structure", pdb_id=pdb_id, path=str(path))

    _write_success_marker(outdir, pdb_ids)

    logger.info("Finished retrieving PDBs", outdir=str(outdir))
    click.echo("Done!")
