# modules/local/docking_run/src/docking_run/providers/unidock_gpu.py

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from docking_run.types import DockingError, DockingResult, SearchBox

from .provider import DockingProvider, ProviderNotAvailableError
from .utils import parse_vina_output_pdbqt

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 1000
_DEFAULT_SEARCH_MODE = "balance"
_DEFAULT_NUM_MODES = 9

_UNIDOCK_BINARY = "unidock"
_SCORING_MODE_VINA = "vina"


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
        receptor_path: Path,
        ligand_path: Path,
        box: SearchBox,
        scoring_mode: str = _SCORING_MODE_VINA,
    ) -> list[DockingResult]:
        results_by_id = dict(
            self._run_gpu_batch(receptor_path, [ligand_path], box, scoring_mode)
        )
        return results_by_id.get(ligand_path.stem, [])

    def dock_batch(
        self,
        receptor_path: Path,
        ligand_paths: list[Path],
        box: SearchBox,
        batch_size: int | None = None,
        scoring_mode: str = _SCORING_MODE_VINA,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        chunk_size = batch_size or _DEFAULT_BATCH_SIZE
        n_chunks = -(-len(ligand_paths) // chunk_size)  # ceil div

        n_ligands_seen = 0
        n_ligands_failed = 0

        for chunk_idx, start in enumerate(range(0, len(ligand_paths), chunk_size), 1):
            chunk = ligand_paths[start : start + chunk_size]
            n_ligands_seen += len(chunk)
            n_yielded_this_chunk = 0

            for ligand_id, results in self._run_gpu_batch(
                receptor_path, chunk, box, scoring_mode
            ):
                n_yielded_this_chunk += 1
                yield ligand_id, results

            n_failed_this_chunk = len(chunk) - n_yielded_this_chunk
            n_ligands_failed += n_failed_this_chunk
            logger.info(
                "unidock chunk %d/%d: %d/%d ligands produced results (%d failed)",
                chunk_idx,
                n_chunks,
                n_yielded_this_chunk,
                len(chunk),
                n_failed_this_chunk,
            )

        if n_ligands_failed:
            logger.warning(
                "unidock dock_batch complete: %d/%d ligands failed to produce "
                "results across %d chunk(s). See preceding WARNING/ERROR log "
                "lines for per-ligand detail.",
                n_ligands_failed,
                n_ligands_seen,
                n_chunks,
            )

    def _run_gpu_batch(
        self,
        receptor_path: Path,
        ligand_paths: list[Path],
        box: SearchBox,
        scoring_mode: str = _SCORING_MODE_VINA,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        chunk_out_dir = self._chunk_out_dir(ligand_paths)
        chunk_out_dir.mkdir(parents=True, exist_ok=True)

        ligand_index_path = chunk_out_dir / "ligand_index.txt"
        ligand_index_path.write_text("\n".join(str(lig) for lig in ligand_paths))

        cmd = [
            _UNIDOCK_BINARY,
            "--receptor",
            str(receptor_path),
            "--ligand_index",
            str(ligand_index_path),
            "--search_mode",
            self.search_mode,
            "--scoring",
            scoring_mode,
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

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise DockingError(
                f"unidock --gpu_batch failed for chunk of {len(ligand_paths)} "
                f"ligands (receptor={receptor_path.name}, "
                f"returncode={proc.returncode}): {proc.stderr.strip()}"
            )

        for lig in ligand_paths:
            ligand_id = lig.stem
            candidates = list(chunk_out_dir.glob(f"{ligand_id}_out.pdbqt"))

            if not candidates:
                logger.warning(
                    "unidock produced no output file for ligand '%s' "
                    "(expected %s) -- skipping. This ligand will be "
                    "absent from results.",
                    ligand_id,
                    chunk_out_dir / f"{ligand_id}_out.pdbqt",
                )
                continue

            if len(candidates) > 1:
                logger.error(
                    "Ambiguous output for ligand '%s' in %s: found %d "
                    "matching files (%s) -- skipping rather than "
                    "guessing which is correct.",
                    ligand_id,
                    chunk_out_dir,
                    len(candidates),
                    [c.name for c in candidates],
                )
                continue

            try:
                results = parse_vina_output_pdbqt(candidates[0], ligand_id=ligand_id)
            except DockingError as exc:
                logger.warning(
                    "Failed to parse unidock output for ligand '%s' "
                    "(%s) -- skipping: %s",
                    ligand_id,
                    candidates[0],
                    exc,
                )
                continue

            if results:
                yield ligand_id, results
            else:
                logger.warning(
                    "unidock output for ligand '%s' (%s) parsed to zero "
                    "poses -- skipping.",
                    ligand_id,
                    candidates[0],
                )

    def _chunk_out_dir(self, ligand_pdbqts: list[Path]) -> Path:
        """Give each chunk its own subdirectory so output filenames
        from different chunks can't collide, and so a chunk's outputs
        are easy to isolate for debugging a specific failed invocation.
        """
        first_id = ligand_pdbqts[0].stem if ligand_pdbqts else "empty"
        return self.out_dir / f"chunk_{first_id}"
