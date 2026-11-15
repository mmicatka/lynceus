# projects/lynceus-dock/src/lynceus_dock/run_docking.py


import datetime
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

import click
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest as LynceusManifest
from protein_ensemble import Manifest
from protein_ensemble.accessors.pdbqt import member_to_pdbqt

from lynceus_dock.common.ligand import iter_ligand_records
from lynceus_dock.common.results import write_results
from lynceus_dock.registry.common import ProviderNotAvailableError
from lynceus_dock.registry.registry import get_provider

from .common.types import DockingError, LigandRecord, SearchBox

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"

NUM_DOCKED_KEY = "num_docked"

MANIFEST_FILENAME = "docking.manifest.json"

logger = get_lynceus_logger()


@dataclass(frozen=True)
class DockingJob:
    ensemble: Path
    member_id: str
    ligands_path: str
    box: SearchBox
    site_id: str
    search_mode: str
    num_modes: int
    batch_size: int | None
    parquet_batch_rows: int
    default_altloc: str
    allow_bad_residues: bool
    keep_docking_output: bool


def _input_manifest(
    ligands_path: str,
    output_path: str,
    source_root: Path,
    expected_state: dict,
) -> LynceusManifest:
    manifest_path = Path(output_path) / MANIFEST_FILENAME
    return LynceusManifest(
        filepath=manifest_path, data=expected_state
    ).set_source_files([ligands_path], source_root)


def _is_run_complete(manifest: LynceusManifest) -> bool:
    try:
        return manifest.exists_superset()
    except Exception as exc:
        logger.warning(
            "Failed to load existing manifest, re-generating.", error=str(exc)
        )
        return False


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


def _dock_and_write(
    provider,
    receptor_path: Path,
    ligands: list[LigandRecord],
    job: DockingJob,
    output_path: str,
) -> int:
    results = provider.dock_batch(
        receptor_path=receptor_path,
        ligands=ligands,
        box=job.box,
        batch_size=job.batch_size,
    )
    try:
        return write_results(
            results,
            output_path,
            member_id=job.member_id,
            site_id=job.site_id,
            batch_rows=job.parquet_batch_rows,
            drop_pose_column=True,
        )
    except DockingError as exc:
        raise click.ClickException(str(exc)) from exc


def _run_job(job: DockingJob, output_path: str) -> int:
    provider = _build_provider(
        job.search_mode, job.num_modes, output_path, job.keep_docking_output
    )
    pdbqt_string = _prepare_receptor_pdbqt(
        job.ensemble,
        job.member_id,
        default_altloc=job.default_altloc,
        allow_bad_residues=job.allow_bad_residues,
    )
    ligands = _load_ligands(job.ligands_path)
    logger.info(
        "Starting docking run",
        ligand_count=len(ligands),
        ligands_path=job.ligands_path,
    )

    with _receptor_file(job.member_id, pdbqt_string) as receptor_path:
        return _dock_and_write(provider, receptor_path, ligands, job, output_path)


def _dock_via_staged_output(
    job: DockingJob, output_path: Path, scratch_dir: str | None
) -> int:
    with staged_output(
        output_path,
        transfers=STAGED_OUTPUT_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        return _run_job(job, str(local_output))


@click.command(help="Dock candidate conformers against a receptor.")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
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
    type=click.Path(exists=True, dir_okay=False),
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
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for docking output before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def run_docking(
    source_root: Path,
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
    scratch_dir: str | None,
) -> None:
    click.echo(
        f"Running docking for {ensemble}:{member_id} with ligands {ligands_path}..."
    )

    expected_state = {
        "ensemble": str(ensemble),
        "member_id": member_id,
        "site_id": site_id,
        "center": list(center),
        "size": list(size),
        "search_mode": search_mode,
        "num_modes": num_modes,
    }
    manifest = _input_manifest(ligands_path, output_path, source_root, expected_state)

    if _is_run_complete(manifest):
        logger.info("Valid manifest found.", manifest=manifest.data)
        click.echo("Done!")
        return

    job = DockingJob(
        ensemble=ensemble,
        member_id=member_id,
        ligands_path=ligands_path,
        box=SearchBox(center=center, size=size),
        site_id=site_id,
        search_mode=search_mode,
        num_modes=num_modes,
        batch_size=batch_size,
        parquet_batch_rows=parquet_batch_rows,
        default_altloc=default_altloc,
        allow_bad_residues=allow_bad_residues,
        keep_docking_output=keep_docking_output,
    )

    logger.info(
        "Executing docking",
        output_path=output_path,
        source_root=str(source_root),
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    manifest.data[NUM_DOCKED_KEY] = _dock_via_staged_output(
        job, Path(output_path), scratch_dir
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished docking run",
        manifest=manifest.data,
        elapsed_time=elapsed_time,
    )
    click.echo("Done!")
