# modules/local/docking_run/src/docking_run/providers/vina_gpu.py

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


_DEFAULT_BATCH_SIZE = 64
_DEFAULT_THREAD = (
    1000  # Vina-GPU+ README default; keep < 10000 per its Limitation table
)
_MAX_THREAD = 10000
_DEFAULT_BINARY_NAME = "Vina-GPU+"


class VinaGPUProvider(DockingProvider):
    def __init__(
        self,
        binary_path: str | Path | None = None,
        search_depth: int | None = None,
        thread: int = _DEFAULT_THREAD,
        default_batch_size: int = _DEFAULT_BATCH_SIZE,
        out_dir: Path | None = None,
    ) -> None:
        self.binary_path = str(binary_path) if binary_path else _DEFAULT_BINARY_NAME
        self.search_depth = search_depth
        self.thread = thread
        self.default_batch_size = default_batch_size
        self.out_dir = out_dir or Path.cwd() / "vina_gpu_out"

    def validate_environment(self) -> None:
        resolved = shutil.which(self.binary_path)
        if resolved is None and not Path(self.binary_path).is_file():
            raise ProviderNotAvailableError(
                f"Vina-GPU+ binary '{self.binary_path}' not found on PATH or as a "
                "file path. Build/install Vina-GPU-2.0 (the Vina-GPU+ target) and "
                "either place it on PATH or pass binary_path= explicitly."
            )
        if self.thread > _MAX_THREAD:
            raise ProviderNotAvailableError(
                f"thread={self.thread} exceeds Vina-GPU+'s documented limit "
                f"(preferably < {_MAX_THREAD} docking lanes)."
            )

    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: SearchBox,
    ) -> list[DockingResult]:
        result_map = self.dock_batch(
            receptor_pdbqt=receptor_pdbqt,
            ligand_pdbqts=[ligand_pdbqt],
            box=box,
            batch_size=1,
        )
        return result_map.get(ligand_pdbqt.stem, [])

    def dock_batch(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
    ) -> dict[str, list[DockingResult]]:
        if not ligand_pdbqts:
            return {}

        effective_batch_size = batch_size or self.default_batch_size
        self.out_dir.mkdir(parents=True, exist_ok=True)

        all_results: dict[str, list[DockingResult]] = {}
        for chunk in _chunk(ligand_pdbqts, effective_batch_size):
            all_results.update(
                self._dock_chunk(
                    receptor_pdbqt=receptor_pdbqt, ligand_pdbqts=chunk, box=box
                )
            )
        return all_results

    def _dock_chunk(
        self,
        *,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
    ) -> dict[str, list[DockingResult]]:
        with tempfile.TemporaryDirectory(prefix="vina_gpu_batch_") as tmp:
            ligand_dir = Path(tmp) / "ligands"
            ligand_dir.mkdir()
            # --ligand_directory takes a directory, not a file list, so
            # stage symlinks rather than requiring the caller's ligand
            # files to already live together in one directory.
            for lig in ligand_pdbqts:
                (ligand_dir / lig.name).symlink_to(lig.resolve())

            cmd = [
                self.binary_path,
                "--receptor",
                str(receptor_pdbqt),
                "--ligand_directory",
                str(ligand_dir),
                "--thread",
                str(self.thread),
                "--center_x",
                str(box.center[0]),
                "--center_y",
                str(box.center[1]),
                "--center_z",
                str(box.center[2]),
                "--size_x",
                str(box.size[0]),
                "--size_y",
                str(box.size[1]),
                "--size_z",
                str(box.size[2]),
            ]
            if self.search_depth is not None:
                cmd += ["--search_depth", str(self.search_depth)]

            # cwd matters: output location isn't documented (see module
            # docstring), so run from self.out_dir and check both there
            # and inside ligand_dir when locating results.
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.out_dir)
            if proc.returncode != 0:
                raise DockingError(
                    f"Vina-GPU+ batch invocation failed (exit {proc.returncode}).\n"
                    f"cmd: {' '.join(cmd)}\nstderr:\n{proc.stderr}"
                )

            results: dict[str, list[DockingResult]] = {}
            for lig in ligand_pdbqts:
                ligand_id = lig.stem
                output_pdbqt = _locate_output_pdbqt(
                    ligand_id=ligand_id, ligand_dir=ligand_dir, out_dir=self.out_dir
                )
                results[ligand_id] = parse_vina_output_pdbqt(
                    output_pdbqt, ligand_id=ligand_id
                )
            return results


def _locate_output_pdbqt(*, ligand_id: str, ligand_dir: Path, out_dir: Path) -> Path:
    candidates = [
        out_dir / f"{ligand_id}_out.pdbqt",
        ligand_dir / f"{ligand_id}_out.pdbqt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise DockingError(
        f"Could not locate Vina-GPU+ output for ligand '{ligand_id}'. Checked: "
        f"{[str(c) for c in candidates]}. The output naming/location convention "
        "used here is an unverified guess (see vina_gpu.py module docstring) — "
        "inspect actual Vina-GPU+ output on disk and update _locate_output_pdbqt()."
    )


def _chunk(items: list[Path], size: int) -> list[list[Path]]:
    if size <= 0:
        raise ValueError(f"batch_size must be positive, got {size}")
    return [items[i : i + size] for i in range(0, len(items), size)]
