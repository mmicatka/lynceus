# modules/local/docking_run/src/docking_run/cli.py

import logging
import sys
import tempfile
from pathlib import Path

import click
from protein_ensemble.accessors.pdbqt import member_to_pdbqt
from protein_ensemble.manifest import Manifest

from .io import (
    DEFAULT_STREAM_BATCH_ROWS,
    iter_ligand_records,
    write_docking_results_parquet,
)
from .providers import ProviderNotAvailableError, get_provider
from .types import DockingError, SearchBox

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


@click.command(
    help=(
        "Dock a Parquet file of candidate conformers (RDKit Mol bytes) "
        "against a receptor, writing ranked poses to Parquet."
    )
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
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Parquet file of candidate conformers (ligand_id, mol_bytes columns).",
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
    required=True,
    help="Search box size, Angstroms (X Y Z).",
)
@click.option(
    "--conformational-state-id",
    type=str,
    required=True,
    help=(
        "Identifier of the receptor conformational state (PCE member "
        "id) being docked against. Recorded on every output row."
    ),
)
@click.option(
    "--site-id",
    type=str,
    required=True,
    help=(
        "Identifier of the binding site being targeted by "
        "--center/--size. Recorded on every output row."
    ),
)
@click.option(
    "--search-mode",
    type=str,
    default="balance",
    show_default=True,
    help="Uni-Dock --search_mode (e.g. 'fast', 'balance', 'detail').",
)
@click.option(
    "--num-modes",
    type=int,
    default=9,
    show_default=True,
    help="Number of output poses per ligand (--num_modes).",
)
@click.option(
    "--batch-size",
    type=int,
    default=None,
    help=(
        "Max ligands per underlying provider invocation. Chunks "
        "ligands into groups of at most this size per unidock "
        "invocation. Defaults to the provider's own default."
    ),
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for provider output files. Defaults to ./unidock_gpu_out.",
)
@click.option(
    "--out-parquet",
    type=click.Path(path_type=Path),
    required=True,
    help=(
        "Path to write docking results as a row-per-pose Parquet "
        "file with catalog_id, conformational_state_id, and site_id columns."
    ),
)
@click.option(
    "--parquet-batch-rows",
    type=int,
    default=DEFAULT_STREAM_BATCH_ROWS,
    show_default=True,
    help=(
        "Max pose-rows buffered per RecordBatch before flushing to "
        "the Parquet writer. Lower to bound peak memory in "
        "memory-constrained containers."
    ),
)
@click.option(
    "--default-altloc",
    default="A",
    show_default=True,
    type=str,
    help="Alternate location identifier to keep when resolving altlocs.",
)
@click.option(
    "--allow-bad-residues",
    is_flag=True,
    help="Drop residues that fail template matching instead of raising.",
)
def docking_run(
    ensemble: Path,
    member_id: str,
    ligands_path: Path,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    conformational_state_id: str,
    site_id: str,
    search_mode: str,
    num_modes: int,
    batch_size: int | None,
    out_dir: Path | None,
    out_parquet: Path,
    parquet_batch_rows: int,
    default_altloc: str,
    allow_bad_residues: bool,
) -> None:
    provider_kwargs = {"search_mode": search_mode, "num_modes": num_modes}
    if out_dir:
        provider_kwargs["out_dir"] = out_dir

    provider = get_provider("gpu", **provider_kwargs)

    try:
        provider.validate_environment()
    except ProviderNotAvailableError as exc:
        raise click.ClickException(str(exc))

    ligands = list(iter_ligand_records(ligands_path))
    if not ligands:
        raise click.ClickException(f"No ligand records found in {ligands_path}")

    box = SearchBox(center=center, size=size)

    logger.info("preparing receptor for member: %s", member_id)
    manifest = Manifest.load(str(ensemble))
    member = manifest.get_member(member_id)
    structure_path = manifest.structure_path(member_id)

    try:
        pdbqt_string = member_to_pdbqt(
            member,
            structure_path,
            default_altloc=default_altloc,
            allow_bad_residues=allow_bad_residues,
        )
    except Exception as exc:
        raise click.ClickException(
            f"Receptor preparation failed for {member_id!r}: {exc}"
        )

    with tempfile.TemporaryDirectory(prefix="docking_receptor_") as tmp:
        receptor_path = Path(tmp) / f"{member_id}.pdbqt"
        receptor_path.write_text(pdbqt_string)

        results_iter = provider.dock_batch(
            receptor_path=receptor_path,
            ligands=ligands,
            box=box,
            batch_size=batch_size,
        )

        try:
            write_docking_results_parquet(
                results_iter,
                out_parquet,
                conformational_state_id=conformational_state_id,
                site_id=site_id,
                batch_rows=parquet_batch_rows,
            )
        except DockingError as exc:
            raise click.ClickException(str(exc))

    logger.info("Wrote docking results to %s", out_parquet)
