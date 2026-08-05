from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from tqdm import tqdm

from docking_run.types import (
    DockingError,
    DockingResult,
    SearchBox,
)
from docking_run.utils import parse_vina_output_pdbqt

from .provider import DockingProvider, ProviderNotAvailableError

_DEFAULT_N_POSES = 9
_DEFAULT_EXHAUSTIVENESS = 8

_LOG_UPDATES = 100


@contextmanager
def suppress_stderr():
    """Context manager to redirect low-level C++ stderr to devnull."""
    stderr_fd = 2
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stderr_fd = os.dup(stderr_fd)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(saved_stderr_fd, stderr_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)


class VinaCPUProvider(DockingProvider):
    """Docking via AutoDock Vina's CPU implementation."""

    def __init__(
        self,
        exhaustiveness: int = _DEFAULT_EXHAUSTIVENESS,
        n_poses: int = _DEFAULT_N_POSES,
        n_workers: int = 1,
        out_dir: Path | None = None,
    ) -> None:
        self.exhaustiveness = exhaustiveness
        self.n_poses = n_poses
        self.n_workers = n_workers
        self.out_dir = out_dir or Path.cwd() / "vina_cpu_out"

    def validate_environment(self) -> None:
        try:
            import vina  # noqa: F401
        except ImportError as exc:
            raise ProviderNotAvailableError(
                "The 'vina' Python package is not installed. "
                "Install with: uv pip install vina"
            ) from exc

    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: SearchBox,
    ) -> list[DockingResult]:
        return _dock_one(
            receptor_pdbqt=receptor_pdbqt,
            ligand_pdbqt=ligand_pdbqt,
            box=box,
            exhaustiveness=self.exhaustiveness,
            n_poses=self.n_poses,
            out_dir=self.out_dir,
        )

    def dock_batch(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        del batch_size

        self.out_dir.mkdir(parents=True, exist_ok=True)

        if self.n_workers <= 1:
            for lig in tqdm(
                ligand_pdbqts,
                desc="Docking ligands",
                unit="ligand",
                dynamic_ncols=True,
                miniters=_LOG_UPDATES,
                mininterval=0,
            ):
                result = _dock_one(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=lig,
                    box=box,
                    exhaustiveness=self.exhaustiveness,
                    n_poses=self.n_poses,
                    out_dir=self.out_dir,
                )
                if result:
                    yield result[0].ligand_id, result
        else:
            with ProcessPoolExecutor(max_workers=self.n_workers) as pool:
                future_to_lig = {
                    pool.submit(
                        _dock_one,
                        receptor_pdbqt=receptor_pdbqt,
                        ligand_pdbqt=lig,
                        box=box,
                        exhaustiveness=self.exhaustiveness,
                        n_poses=self.n_poses,
                        out_dir=self.out_dir,
                    ): lig
                    for lig in ligand_pdbqts
                }

                with tqdm(
                    total=len(future_to_lig),
                    desc="Docking ligands (parallel)",
                    unit="ligand",
                    dynamic_ncols=True,
                    miniters=_LOG_UPDATES,
                    mininterval=0,
                ) as pbar:
                    for future in as_completed(future_to_lig):
                        result = future.result()
                        pbar.update(1)
                        if result:
                            yield result[0].ligand_id, result


def _dock_one(
    *,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    box: SearchBox,
    exhaustiveness: int,
    n_poses: int,
    out_dir: Path,
) -> list[DockingResult]:
    """Module-level worker function picklable for ProcessPoolExecutor."""
    import vina

    ligand_id = ligand_pdbqt.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdbqt = out_dir / f"{ligand_id}_out.pdbqt"

    with suppress_stderr():
        v = vina.Vina(sf_name="vina", verbosity=0)
        v.set_receptor(str(receptor_pdbqt))
        v.set_ligand_from_file(str(ligand_pdbqt))
        v.compute_vina_maps(center=list(box.center), box_size=list(box.size))
        v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)

        try:
            v.write_poses(str(output_pdbqt), n_poses=n_poses, overwrite=True)
        except Exception as exc:
            raise DockingError(f"Vina docking failed for {ligand_id}: {exc}") from exc

    return parse_vina_output_pdbqt(output_pdbqt, ligand_id=ligand_id)
