# projects/lynceus-dock/src/lynceus_dock/run_docking.py

import sys
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import click
import structlog
from lynceus_core.logging import wide_log
from protein_ensemble.accessors.pdbqt import member_to_pdbqt
from protein_ensemble.manifest import Manifest

from lynceus_dock.common.ligand import count_ligand_rows, iter_ligand_records
from lynceus_dock.common.manifest import (
    build_entry,
    build_manifest_path,
    existing_entry_is_valid,
    load_manifest,
    run_key,
    write_manifest,
)
from lynceus_dock.common.results import write_results
from lynceus_dock.registry.common import ProviderNotAvailableError
from lynceus_dock.registry.registry import get_provider

from .common.types import DockingError, LigandRecord, SearchBox

warnings.filterwarnings("ignore", category=SyntaxWarning)


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
logger = structlog.get_logger()


def _already_docked(
    manifest: dict[str, Any],
    key: str,
    *,
    member_id: str,
    site_id: str,
    ligands_path: str,
    ligand_row_count: int,
) -> bool:
    existing_entry = manifest["runs"].get(key)
    if existing_entry is None:
        return False

    existing_entry_is_valid(existing_entry, ligands_path, ligand_row_count)
    logger.info(
        "Skipping already docked target",
        member_id=member_id,
        site_id=site_id,
        pose_row_count=existing_entry["pose_row_count"],
        ligand_row_count=ligand_row_count,
        out_parquet=existing_entry["out_parquet"],
    )
    return True


def _build_provider(search_mode: str, num_modes: int, out_dir: Path | None):
    provider_kwargs: dict[str, Any] = {
        "search_mode": search_mode,
        "num_modes": num_modes,
    }
    if out_dir:
        provider_kwargs["out_dir"] = out_dir

    provider = get_provider("gpu", **provider_kwargs)
    try:
        provider.validate_environment()
    except ProviderNotAvailableError as exc:
        raise click.ClickException(str(exc)) from exc
    return provider


def _load_ligands(ligands_path: str) -> list[LigandRecord]:
    ligands = list(iter_ligand_records(ligands_path))
    if not ligands:
        raise click.ClickException(f"No ligand records found in {ligands_path}")
    return ligands


def _prepare_receptor_pdbqt(
    ensemble: Path,
    member_id: str,
    *,
    default_altloc: str,
    allow_bad_residues: bool,
) -> str:
    logger.info("Preparing receptor for member", member_id=member_id)
    ensemble_manifest = Manifest.load(ensemble)
    member = ensemble_manifest.get_member(member_id)
    structure_path = ensemble_manifest.structure_path(member_id)

    try:
        return member_to_pdbqt(
            member,
            structure_path,
            default_altloc=default_altloc,
            allow_bad_residues=allow_bad_residues,
        )
    except Exception as exc:
        raise click.ClickException(
            f"Receptor preparation failed for {member_id!r}: {exc}"
        ) from exc


@contextmanager
def _receptor_file(member_id: str, pdbqt_string: str) -> Generator[Path]:
    with tempfile.TemporaryDirectory(prefix="docking_receptor_") as tmp:
        receptor_path = Path(tmp) / f"{member_id}.pdbqt"
        receptor_path.write_text(pdbqt_string)
        yield receptor_path


def _dock_and_write(
    provider,
    receptor_path: Path,
    ligands: list[LigandRecord],
    box: SearchBox,
    *,
    batch_size: int | None,
    out_parquet: str,
    conformational_state_id: str,
    site_id: str,
    parquet_batch_rows: int,
) -> int:
    results_iter = provider.dock_batch(
        receptor_path=receptor_path,
        ligands=ligands,
        box=box,
        batch_size=batch_size,
    )
    try:
        return write_results(
            results_iter,
            out_parquet,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            batch_rows=parquet_batch_rows,
            drop_pose_column=True,
        )
    except DockingError as exc:
        raise click.ClickException(str(exc)) from exc


def _record_run(
    manifest: dict[str, Any],
    manifest_file_path: Path,
    key: str,
    *,
    member_id: str,
    site_id: str,
    ligands_path: str,
    ligand_row_count: int,
    out_parquet: str,
    pose_row_count: int,
) -> None:
    manifest["runs"][key] = build_entry(
        member_id,
        site_id,
        ligands_path,
        ligand_row_count,
        out_parquet,
        pose_row_count,
    )
    write_manifest(manifest_file_path, manifest)


@wide_log(logger)
def run_docking(
    ensemble: Path,
    member_id: str,
    ligands_path: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    conformational_state_id: str,
    site_id: str,
    search_mode: str,
    num_modes: int,
    batch_size: int | None,
    out_dir: Path | None,
    out_parquet: str,
    parquet_batch_rows: int,
    default_altloc: str,
    allow_bad_residues: bool,
) -> None:
    click.echo(f"Processing docking run for {ligands_path}...")

    ligand_row_count = count_ligand_rows(ligands_path)
    logger.info(
        "Preparing ligands",
        ligand_row_count=ligand_row_count,
        ligands_path=ligands_path,
    )

    manifest_path = build_manifest_path(out_parquet)
    manifest = load_manifest(manifest_path)
    key = run_key(member_id, site_id)

    if _already_docked(
        manifest,
        key,
        member_id=member_id,
        site_id=site_id,
        ligands_path=ligands_path,
        ligand_row_count=ligand_row_count,
    ):
        click.echo("Done!")
        return

    provider = _build_provider(search_mode, num_modes, out_dir)
    ligands = _load_ligands(ligands_path)
    box = SearchBox(center=center, size=size)
    pdbqt_string = _prepare_receptor_pdbqt(
        ensemble,
        member_id,
        default_altloc=default_altloc,
        allow_bad_residues=allow_bad_residues,
    )

    with _receptor_file(member_id, pdbqt_string) as receptor_path:
        pose_row_count = _dock_and_write(
            provider,
            receptor_path,
            ligands,
            box,
            batch_size=batch_size,
            out_parquet=out_parquet,
            conformational_state_id=conformational_state_id,
            site_id=site_id,
            parquet_batch_rows=parquet_batch_rows,
        )

    _record_run(
        manifest,
        manifest_path,
        key,
        member_id=member_id,
        site_id=site_id,
        ligands_path=ligands_path,
        ligand_row_count=ligand_row_count,
        out_parquet=out_parquet,
        pose_row_count=pose_row_count,
    )

    logger.info(
        "Finished docking run",
        out_parquet=out_parquet,
        manifest_file_path=manifest_path,
    )
    click.echo("Done!")
