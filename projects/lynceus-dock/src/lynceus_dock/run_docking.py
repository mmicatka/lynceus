# projects/lynceus-dock/src/lynceus_dock/run_docking.py

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

import click
from lynceus_core.logging import get_lynceus_logger, wide_log
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

logger = get_lynceus_logger()


@dataclass(frozen=True)
class RunIdentity:
    member_id: str
    site_id: str
    ligands_path: str
    ligand_row_count: int
    out_parquet: str

    @property
    def key(self) -> str:
        return run_key(self.member_id, self.site_id)


def _already_docked(manifest: dict[str, Any], identity: RunIdentity) -> bool:
    existing_entry = manifest["runs"].get(identity.key)
    if existing_entry is None:
        return False
    if not existing_entry_is_valid(
        existing_entry, identity.ligands_path, identity.ligand_row_count
    ):
        return False

    logger.info(
        "Skipping already docked target",
        member_id=identity.member_id,
        site_id=identity.site_id,
        pose_row_count=existing_entry["pose_row_count"],
        ligand_row_count=identity.ligand_row_count,
        out_parquet=existing_entry["out_parquet"],
    )
    return True


def _ensure_output_parent(out_parquet: str) -> None:
    Path(out_parquet).parent.mkdir(parents=True, exist_ok=True)


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
    try:
        ensemble_manifest = Manifest.load(ensemble)
        member = ensemble_manifest.get_member(member_id)
        structure_path = ensemble_manifest.structure_path(member_id)
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
def _receptor_file(member_id: str, pdbqt_string: str) -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory(prefix="docking_receptor_") as tmp:
        receptor_path = Path(tmp) / f"{member_id}.pdbqt"
        receptor_path.write_text(pdbqt_string)
        yield receptor_path


def _dock_and_write(
    provider,
    receptor_path: Path,
    ligands: list[LigandRecord],
    box: SearchBox,
    identity: RunIdentity,
    *,
    member_id: str,
    batch_size: int | None,
    parquet_batch_rows: int,
) -> int:
    results = provider.dock_batch(
        receptor_path=receptor_path,
        ligands=ligands,
        box=box,
        batch_size=batch_size,
    )
    try:
        return write_results(
            results,
            identity.out_parquet,
            member_id=member_id,
            site_id=identity.site_id,
            batch_rows=parquet_batch_rows,
            drop_pose_column=True,
        )
    except DockingError as exc:
        raise click.ClickException(str(exc)) from exc


def _record_run(
    manifest: dict[str, Any],
    manifest_file_path: Path,
    identity: RunIdentity,
    pose_row_count: int,
) -> None:
    manifest["runs"][identity.key] = build_entry(
        identity.member_id,
        identity.site_id,
        identity.ligands_path,
        identity.ligand_row_count,
        identity.out_parquet,
        pose_row_count,
    )
    write_manifest(manifest_file_path, manifest)


@click.command(help="Dock candidate conformers against a receptor.")
@click.option(
    "--ensemble",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Protein conformational ensemble package directory.",
)
@click.option(
    "--member-id",
    type=str,
    required=True,
    help="Id of the ensemble member to prepare and dock against as the receptor.",
)
@click.option(
    "--ligands-path",
    type=str,
    required=True,
    help="Parquet file of candidate conformers.",
)
@click.option(
    "--center",
    type=(float, float, float),
    required=True,
    help="Search box center, Angstroms (X Y Z).",
)
@click.option(
    "--size",
    type=(float, float, float),
    default=(25.0, 25.0, 25.0),
    show_default=True,
    help="Search box size, Angstroms (X Y Z).",
)
@click.option(
    "--site-id", type=str, required=True, help="Identifier of the binding site."
)
@click.option(
    "--search-mode",
    type=str,
    default="balance",
    show_default=True,
    help="Uni-Dock search mode.",
)
@click.option(
    "--num-modes",
    type=int,
    default=9,
    show_default=True,
    help="Number of output poses per ligand.",
)
@click.option(
    "--batch-size",
    type=int,
    default=None,
    help="Max ligands per underlying provider invocation.",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for provider output files.",
)
@click.option(
    "--out-parquet",
    type=str,
    required=True,
    help="Path to write docking results as Parquet.",
)
@click.option(
    "--parquet-batch-rows",
    type=int,
    default=10000,
    show_default=True,
    help="Max pose-rows buffered per RecordBatch.",
)
@click.option(
    "--default-altloc",
    type=str,
    default="A",
    show_default=True,
    help="Alternate location identifier to keep.",
)
@click.option(
    "--allow-bad-residues",
    is_flag=True,
    help="Drop residues that fail template matching instead of raising.",
)
@wide_log(logger)
def run_docking(
    ensemble: Path,
    member_id: str,
    ligands_path: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
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
    identity = RunIdentity(
        member_id=member_id,
        site_id=site_id,
        ligands_path=ligands_path,
        ligand_row_count=count_ligand_rows(ligands_path),
        out_parquet=out_parquet,
    )
    logger.info(
        "Starting docking run",
        ligand_row_count=identity.ligand_row_count,
        ligands_path=ligands_path,
    )

    manifest_path = build_manifest_path(out_parquet)
    manifest = load_manifest(manifest_path)
    if _already_docked(manifest, identity):
        return

    _ensure_output_parent(out_parquet)
    provider = _build_provider(search_mode, num_modes, out_dir)
    pdbqt_string = _prepare_receptor_pdbqt(
        ensemble,
        member_id,
        default_altloc=default_altloc,
        allow_bad_residues=allow_bad_residues,
    )
    ligands = _load_ligands(ligands_path)
    box = SearchBox(center=center, size=size)

    with _receptor_file(member_id, pdbqt_string) as receptor_path:
        pose_row_count = _dock_and_write(
            provider,
            receptor_path,
            ligands,
            box,
            identity,
            member_id=member_id,
            batch_size=batch_size,
            parquet_batch_rows=parquet_batch_rows,
        )

    _record_run(manifest, manifest_path, identity, pose_row_count)
    logger.info(
        "Finished docking run",
        out_parquet=out_parquet,
        manifest_file_path=manifest_path,
        pose_row_count=pose_row_count,
    )
