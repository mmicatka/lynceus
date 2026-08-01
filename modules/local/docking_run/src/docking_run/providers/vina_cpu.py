# modules/local/docking_run/src/docking_run/providers/vina_cpu.py


from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from docking_run.types import (
    DockingError,
    DockingResult,
    SearchBox,
)
from docking_run.utils import parse_vina_output_pdbqt

from .provider import DockingProvider, ProviderNotAvailableError

_DEFAULT_N_POSES = 9
_DEFAULT_EXHAUSTIVENESS = 8


class VinaCPUProvider(DockingProvider):
    """Docking via AutoDock Vina's CPU implementation.

    FIXME: exhaustiveness is CPU Vina's actual search-thoroughness knob;
    it is NOT ported to VinaGPUProvider, which uses a different parameter
    (search_depth) with different semantics. Do not assume equivalent
    values produce comparable search thoroughness across providers.
    """

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
    ) -> dict[str, list[DockingResult]]:
        # batch_size has no meaning for a non-batched backend: there's no
        # underlying invocation to chunk. We accept the parameter (to
        # satisfy the interface / keep CLI plumbing uniform) but ignore it,
        # per the ABC docstring's "providers with no native batch
        # primitive may ignore this" contract.
        del batch_size

        self.out_dir.mkdir(parents=True, exist_ok=True)

        if self.n_workers <= 1:
            results = [
                _dock_one(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=lig,
                    box=box,
                    exhaustiveness=self.exhaustiveness,
                    n_poses=self.n_poses,
                    out_dir=self.out_dir,
                )
                for lig in ligand_pdbqts
            ]
        else:
            with ProcessPoolExecutor(max_workers=self.n_workers) as pool:
                futures = [
                    pool.submit(
                        _dock_one,
                        receptor_pdbqt=receptor_pdbqt,
                        ligand_pdbqt=lig,
                        box=box,
                        exhaustiveness=self.exhaustiveness,
                        n_poses=self.n_poses,
                        out_dir=self.out_dir,
                    )
                    for lig in ligand_pdbqts
                ]
                results = [f.result() for f in futures]

        return {r[0].ligand_id: r for r in results if r}


def _dock_one(
    *,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    box: SearchBox,
    exhaustiveness: int,
    n_poses: int,
    out_dir: Path,
) -> list[DockingResult]:
    """Module-level (not a method) so it's picklable for ProcessPoolExecutor."""
    import vina

    ligand_id = ligand_pdbqt.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdbqt = out_dir / f"{ligand_id}_out.pdbqt"

    v = vina.Vina(sf_name="vina")
    v.set_receptor(str(receptor_pdbqt))
    v.set_ligand_from_file(str(ligand_pdbqt))
    v.compute_vina_maps(center=list(box.center), box_size=list(box.size))
    v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)

    try:
        v.write_poses(str(output_pdbqt), n_poses=n_poses, overwrite=True)
    except Exception as exc:  # vina bindings raise plain Exception on failure
        raise DockingError(f"Vina docking failed for {ligand_id}: {exc}") from exc

    return parse_vina_output_pdbqt(output_pdbqt, ligand_id=ligand_id)
