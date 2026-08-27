# modules/local/docking_run/src/docking_run/providers/unidock_gpu.py

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from docking_run.ligand_prep import materialize_ligands
from docking_run.types import DockingError, DockingResult, LigandRecord, SearchBox

from .provider import DockingProvider, ProviderNotAvailableError
from .utils import parse_vina_output_pdbqt

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 1000
_DEFAULT_SEARCH_MODE = "balance"
_DEFAULT_NUM_MODES = 9

_UNIDOCK_BINARY = "unidock"
_SCORING_MODE_VINA = "vina"


_MAX_CRASH_RETRIES_PER_BATCH = 1
_MIN_BISECT_SIZE = 1


class UnidockCrashQuarantine:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def add(self, ligand_ids: list[str], reason: str) -> None:
        for ligand_id in ligand_ids:
            self.entries.append({"ligand_id": ligand_id, "reason": reason})

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)


class UnidockGPUProvider(DockingProvider):
    def __init__(
        self,
        search_mode: str = _DEFAULT_SEARCH_MODE,
        num_modes: int = _DEFAULT_NUM_MODES,
        out_dir: Path | None = None,
    ) -> None:
        self.search_mode = search_mode
        self.num_modes = num_modes
        self.out_dir = out_dir or Path.cwd() / "unidock_gpu_out"
        self.quarantine = UnidockCrashQuarantine()

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
        ligand: LigandRecord,
        box: SearchBox,
        scoring_mode: str = _SCORING_MODE_VINA,
    ) -> list[DockingResult]:
        results_by_id = dict(
            self._run_gpu_batch_contained(receptor_path, [ligand], box, scoring_mode)
        )
        return results_by_id.get(ligand.ligand_id, [])

    def dock_batch(
        self,
        receptor_path: Path,
        ligands: list[LigandRecord],
        box: SearchBox,
        batch_size: int | None = None,
        scoring_mode: str = _SCORING_MODE_VINA,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        chunk_size = batch_size or _DEFAULT_BATCH_SIZE
        n_chunks = -(-len(ligands) // chunk_size)  # ceil div

        n_ligands_seen = 0
        n_ligands_failed = 0
        n_ligands_quarantined = 0

        for chunk_idx, start in enumerate(range(0, len(ligands), chunk_size), 1):
            chunk = ligands[start : start + chunk_size]
            n_ligands_seen += len(chunk)
            n_yielded_this_chunk = 0
            n_quarantined_before = len(self.quarantine)

            for ligand_id, results in self._run_gpu_batch_contained(
                receptor_path, chunk, box, scoring_mode
            ):
                n_yielded_this_chunk += 1
                yield ligand_id, results

            n_quarantined_this_chunk = len(self.quarantine) - n_quarantined_before
            n_ligands_quarantined += n_quarantined_this_chunk
            n_failed_this_chunk = len(chunk) - n_yielded_this_chunk
            n_ligands_failed += n_failed_this_chunk
            logger.info(
                "unidock chunk %d/%d: %d/%d ligands produced results "
                "(%d failed, %d quarantined due to crashes)",
                chunk_idx,
                n_chunks,
                n_yielded_this_chunk,
                len(chunk),
                n_failed_this_chunk,
                n_quarantined_this_chunk,
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
        if self.quarantine:
            logger.warning(
                "unidock dock_batch complete: %d ligand(s) quarantined after "
                "repeated subprocess crashes (isolated via bisection). See "
                "provider.quarantine.entries for the full list.",
                n_ligands_quarantined,
            )

    def _run_gpu_batch_contained(
        self,
        receptor_path: Path,
        ligands: list[LigandRecord],
        box: SearchBox,
        scoring_mode: str,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        with materialize_ligands(ligands) as paths_by_id:
            yield from self._run_with_bisection(
                receptor_path, paths_by_id, box, scoring_mode, retries_used=0
            )

    def _run_with_bisection(
        self,
        receptor_path: Path,
        paths_by_id: dict[str, Path],
        box: SearchBox,
        scoring_mode: str,
        retries_used: int,
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        if not paths_by_id:
            return

        chunk_out_dir = self._chunk_out_dir(paths_by_id)

        try:
            crashed = False
            proc = self._invoke_unidock(
                receptor_path, paths_by_id, box, scoring_mode, chunk_out_dir
            )
        except _UnidockCrash as exc:
            crashed = True
            proc = exc.proc

        if crashed:
            logger.error(
                "unidock subprocess crashed (returncode=%d) on a batch of "
                "%d ligand(s) in %s: %s",
                proc.returncode,
                len(paths_by_id),
                chunk_out_dir,
                proc.stderr.strip() if proc.stderr else "(no stderr)",
            )

            recovered, unresolved = self._partition_by_output_present(
                paths_by_id, chunk_out_dir
            )
            for ligand_id, results in self._collect_chunk_results(
                recovered, chunk_out_dir
            ):
                yield ligand_id, results

            if not unresolved:
                return

            if retries_used < _MAX_CRASH_RETRIES_PER_BATCH:
                logger.warning(
                    "Retrying crashed sub-batch of %d ligand(s) once "
                    "(retry %d/%d) before bisecting.",
                    len(unresolved),
                    retries_used + 1,
                    _MAX_CRASH_RETRIES_PER_BATCH,
                )
                yield from self._run_with_bisection(
                    receptor_path,
                    unresolved,
                    box,
                    scoring_mode,
                    retries_used=retries_used + 1,
                )
                return

            if len(unresolved) <= _MIN_BISECT_SIZE:
                ligand_ids = list(unresolved.keys())
                logger.error(
                    "Quarantining %d ligand(s) after repeated unidock "
                    "crashes at minimum bisection size: %s",
                    len(unresolved),
                    ligand_ids,
                )
                self.quarantine.add(
                    ligand_ids,
                    reason=(
                        f"unidock subprocess crashed (returncode="
                        f"{proc.returncode}) and could not be isolated "
                        f"further below batch size {_MIN_BISECT_SIZE}"
                    ),
                )
                return

            items = list(unresolved.items())
            midpoint = len(items) // 2
            left, right = dict(items[:midpoint]), dict(items[midpoint:])
            logger.warning(
                "Bisecting crashed sub-batch of %d ligand(s) into halves "
                "of %d and %d to isolate the failure.",
                len(unresolved),
                len(left),
                len(right),
            )
            yield from self._run_with_bisection(
                receptor_path, left, box, scoring_mode, retries_used=0
            )
            yield from self._run_with_bisection(
                receptor_path, right, box, scoring_mode, retries_used=0
            )
            return

        yield from self._collect_chunk_results(paths_by_id, chunk_out_dir)

    def _invoke_unidock(
        self,
        receptor_path: Path,
        paths_by_id: dict[str, Path],
        box: SearchBox,
        scoring_mode: str,
        chunk_out_dir: Path,
    ) -> subprocess.CompletedProcess:
        chunk_out_dir.mkdir(parents=True, exist_ok=True)

        ligand_index_path = chunk_out_dir / "ligand_index.txt"
        ligand_index_path.write_text("\n".join(str(p) for p in paths_by_id.values()))

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

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise _UnidockCrash(proc)
        return proc

    def _partition_by_output_present(
        self, paths_by_id: dict[str, Path], chunk_out_dir: Path
    ) -> tuple[dict[str, Path], dict[str, Path]]:
        present: dict[str, Path] = {}
        absent: dict[str, Path] = {}
        for ligand_id, path in paths_by_id.items():
            matches = list(chunk_out_dir.glob(f"{ligand_id}_out.pdbqt"))
            (present if matches else absent)[ligand_id] = path
        return present, absent

    def _collect_chunk_results(
        self, paths_by_id: dict[str, Path], chunk_out_dir: Path
    ) -> Iterator[tuple[str, list[DockingResult]]]:
        for ligand_id in paths_by_id:
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

    def _chunk_out_dir(self, paths_by_id: dict[str, Path]) -> Path:
        if not paths_by_id:
            return self.out_dir / "chunk_empty"
        ids = list(paths_by_id.keys())
        return self.out_dir / f"chunk_{ids[0]}_{ids[-1]}_{len(ids)}"


class _UnidockCrash(Exception):
    """Internal signal carrying the failed CompletedProcess so the
    bisection logic can inspect returncode/stderr without re-parsing a
    DockingError message string.
    """

    def __init__(self, proc: subprocess.CompletedProcess) -> None:
        self.proc = proc
        super().__init__(f"unidock crashed with returncode={proc.returncode}")
