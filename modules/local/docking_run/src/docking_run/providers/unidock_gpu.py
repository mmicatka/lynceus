# modules/local/docking_run/src/docking_run/providers/unidock_gpu.py

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from docking_run.types import DockingError, DockingResult, SearchBox

from .provider import DockingProvider, ProviderNotAvailableError

_DEFAULT_BATCH_SIZE = 1000
"""Per Uni-Dock's README FAQ ("Uni-Dock computes slowly for few (<10)
ligands"): throughput is best in the "order of 1000" ligands per batch,
since fixed per-invocation overhead dominates below that and GPU memory
constraints cap how far above it's useful. This is a starting point, not
a tuned value — profile against actual GPU memory / ligand size before
trusting it at scale.
"""

_DEFAULT_SEARCH_MODE = "balance"
_DEFAULT_NUM_MODES = 9

_UNIDOCK_BINARY = "unidock"


class UnidockGPUProvider(DockingProvider):
    def __init__(
        self,
        search_mode: str = _DEFAULT_SEARCH_MODE,
        num_modes: int = _DEFAULT_NUM_MODES,
        max_gpu_memory: int = 0,
        out_dir: Path | None = None,
    ) -> None:
        self.search_mode = search_mode
        self.num_modes = num_modes
        self.max_gpu_memory = max_gpu_memory
        self.out_dir = out_dir or Path.cwd() / "unidock_gpu_out"

    def validate_environment(self) -> None:
        if shutil.which(_UNIDOCK_BINARY) is None:
            raise ProviderNotAvailableError(
                f"'{_UNIDOCK_BINARY}' binary not found on PATH. "
                "Install via conda-forge (conda install -c conda-forge unidock) "
                "or build from source: https://github.com/dptech-corp/Uni-Dock"
            )

    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: SearchBox,
    ) -> list[DockingResult]:
        results_by_id = dict(self._run_gpu_batch(receptor_pdbqt, [ligand_pdbqt], box))
        return results_by_id.get(ligand_pdbqt.stem, [])

    def dock_batch(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        chunk_size = batch_size or _DEFAULT_BATCH_SIZE

        for start in range(0, len(ligand_pdbqts), chunk_size):
            chunk = ligand_pdbqts[start : start + chunk_size]
            yield from self._run_gpu_batch(receptor_pdbqt, chunk, box)

    def _run_gpu_batch(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqts: list[Path],
        box: SearchBox,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        chunk_out_dir = self._chunk_out_dir(ligand_pdbqts)
        chunk_out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            _UNIDOCK_BINARY,
            "--receptor",
            str(receptor_pdbqt),
            "--gpu_batch",
            *[str(lig) for lig in ligand_pdbqts],
            "--search_mode",
            self.search_mode,
            "--scoring",
            "vina",
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
            "--num_modes",
            str(self.num_modes),
            "--dir",
            str(chunk_out_dir),
        ]
        if self.max_gpu_memory:
            cmd += ["--max_gpu_memory", str(self.max_gpu_memory)]

        # Explicit over silent: a failed batch invocation raises rather
        # than silently yielding nothing for every ligand in the chunk.
        # This mirrors the CPU provider's per-ligand DockingError, just
        # scoped to the whole chunk since that's the failure granularity
        # unidock actually gives us.
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise DockingError(
                f"unidock --gpu_batch failed for chunk of {len(ligand_pdbqts)} "
                f"ligands (receptor={receptor_pdbqt.name}, "
                f"returncode={proc.returncode}): {proc.stderr.strip()}"
            )

        for lig in ligand_pdbqts:
            ligand_id = lig.stem
            # FIXME: output filename convention (e.g. whether unidock
            # emits "<ligand_stem>_out.pdbqt" like Vina, or something
            # else under --dir) is an unverified guess. Confirm against
            # an actual --gpu_batch run's --dir contents before trusting
            # this glob.
            candidates = list(chunk_out_dir.glob(f"{ligand_id}*out*.pdbqt"))
            if not candidates:
                # Same silent-drop-on-missing-output policy as
                # VinaCPUProvider: a ligand with no output pose is
                # omitted, not yielded with an empty list.
                continue

            results = _parse_unidock_output_pdbqt(candidates[0], ligand_id=ligand_id)
            if results:
                yield ligand_id, results

    def _chunk_out_dir(self, ligand_pdbqts: list[Path]) -> Path:
        """Give each chunk its own subdirectory so output filenames
        from different chunks can't collide, and so a chunk's outputs
        are easy to isolate for debugging a specific failed invocation.
        """
        first_id = ligand_pdbqts[0].stem if ligand_pdbqts else "empty"
        return self.out_dir / f"chunk_{first_id}"


_RESULT_LINE = re.compile(
    r"^REMARK VINA RESULT:\s*"
    r"(?P<affinity>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_lb>-?\d+\.?\d*)\s+"
    r"(?P<rmsd_ub>-?\d+\.?\d*)",
)


def _parse_unidock_output_pdbqt(
    output_pdbqt: Path, ligand_id: str
) -> list[DockingResult]:
    if not output_pdbqt.is_file():
        raise DockingError(f"Expected output PDBQT not found: {output_pdbqt}")

    text = output_pdbqt.read_text()
    results: list[DockingResult] = []
    mode = 0
    for line in text.splitlines():
        if line.startswith("MODEL"):
            mode += 1
        match = _RESULT_LINE.match(line)
        if match:
            results.append(
                DockingResult(
                    ligand_id=ligand_id,
                    pose_pdbqt=output_pdbqt,
                    affinity_kcal_mol=float(match["affinity"]),
                    mode=mode if mode > 0 else 1,
                    rmsd_lb=float(match["rmsd_lb"]),
                    rmsd_ub=float(match["rmsd_ub"]),
                )
            )

    if not results:
        raise DockingError(
            f"No REMARK VINA RESULT lines found in {output_pdbqt}; "
            "docking may have failed silently."
        )
    return results
