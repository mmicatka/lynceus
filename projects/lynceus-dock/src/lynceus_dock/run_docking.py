# projects/lynceus-dock/src/lynceus_dock/run_docking.py

import datetime
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import click
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest as LynceusManifest
from protein_ensemble import Manifest
from protein_ensemble.accessors.pdbqt import member_to_pdbqt

from lynceus_dock.common.ligand import iter_ligand_records
from lynceus_dock.common.results import write_results
from lynceus_dock.registry.common import ProviderNotAvailableError
from lynceus_dock.registry.registry import get_provider

from .common.types import DockingError, LigandRecord, SearchBox

logger = get_lynceus_logger()

MANIFEST_FILENAME = "docking.manifest.json"


def _build_provider(
    search_mode: str, num_modes: int, output_path: str, keep_docking_output: bool
):
    provider_kwargs: dict[str, Any] = {
        "search_mode": search_mode,
        "num_modes": num_modes,
        "logger": logger,
        "output_path": output_path,
        "keep_docking_output": keep_docking_output,
    }

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


def _is_run_complete(manifest: LynceusManifest) -> bool:
    try:
        return manifest.exists_superset()
    except Exception as exc:
        logger.warning(
            "Failed to load existing manifest, re-generating.", error=str(exc)
        )
        return False


def _dock_and_write(
    provider,
    receptor_path: Path,
    ligands: list[LigandRecord],
    box: SearchBox,
    *,
    member_id: str,
    site_id: str,
    output_path: str,
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
            output_path,
            member_id=member_id,
            site_id=site_id,
            batch_rows=parquet_batch_rows,
            drop_pose_column=True,
        )
    except DockingError as exc:
        raise click.ClickException(str(exc)) from exc


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
    "--output",
    "output_path",
    type=str,
    required=True,
    help="Directory for provider output files.",
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
@click.option(
    "--keep-docking-output",
    is_flag=True,
    help="Keep docking output.",
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
    output_path: str,
    parquet_batch_rows: int,
    default_altloc: str,
    allow_bad_residues: bool,
    keep_docking_output: bool,
) -> None:
    click.echo(
        f"Running docking for {ensemble}:{member_id} with ligands {ligands_path}..."
    )

    start_time = time.perf_counter()

    manifest = LynceusManifest(
        data={
            "ensemble": str(ensemble),
            "member_id": member_id,
            "ligands_path": ligands_path,
            "center": center,
            "size": size,
            "search_mode": search_mode,
            "num_modes": num_modes,
            "output_path": output_path,
        },
        filepath=Path(output_path) / MANIFEST_FILENAME,
    )

    if _is_run_complete(manifest):
        logger.info("Valid manifest found.", manifest=manifest.data)
        click.echo("Done!")
        return

    provider = _build_provider(search_mode, num_modes, output_path, keep_docking_output)
    pdbqt_string = _prepare_receptor_pdbqt(
        ensemble,
        member_id,
        default_altloc=default_altloc,
        allow_bad_residues=allow_bad_residues,
    )
    ligands = _load_ligands(ligands_path)
    logger.info(
        "Starting docking run",
        ligand_count=len(ligands),
        ligands_path=ligands_path,
    )

    with _receptor_file(member_id, pdbqt_string) as receptor_path:
        manifest.data["num_docked"] = _dock_and_write(
            provider,
            receptor_path,
            ligands,
            SearchBox(center=center, size=size),
            member_id=member_id,
            site_id=site_id,
            output_path=output_path,
            batch_size=batch_size,
            parquet_batch_rows=parquet_batch_rows,
        )

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished docking run",
        manifest=manifest.data,
        elapsed_time=elapsed_time,
    )
