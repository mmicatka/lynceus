# modules/local/docking_prep/src/docking_prep/ligand/ligand.py

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from multiprocessing import Pool
from pathlib import Path
from typing import Iterator

import lmdb
import pyarrow.parquet as pq
from rdkit import RDLogger

from docking_prep.ligand.conformer_generation import generate_conformers

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

warnings.filterwarnings("ignore", category=SyntaxWarning, module="prody")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

_LMDB_BATCH_SIZE = 1000


def _parse_num_workers(value: str) -> int:
    if value == "auto":
        return os.cpu_count() or 1
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("workers must be >= 1")
    return n


def _worker_process_candidate(
    args: tuple[str, str, float, float, int, int, float, int],
) -> tuple[str, bytes | None, str | None]:
    (
        candidate_id,
        smiles,
        ph_min,
        ph_max,
        n_confs,
        keep_top_n,
        rmsd_prune_threshold,
        random_seed,
    ) = args
    try:
        result = generate_conformers(
            candidate_id=candidate_id,
            smiles=smiles,
            ph_min=ph_min,
            ph_max=ph_max,
            n_confs=n_confs,
            keep_top_n=keep_top_n,
            rmsd_prune_threshold=rmsd_prune_threshold,
            random_seed=random_seed,
        )
    except Exception as exc:  # noqa: BLE001 - reported per-candidate, not raised
        return candidate_id, None, str(exc)

    if not result.ok:
        return candidate_id, None, result.error

    return candidate_id, result.to_record_bytes(), None


def _iter_candidate_args(
    input_path: Path, args: argparse.Namespace
) -> Iterator[tuple[str, str, float, float, int, int, float, int]]:
    parquet_file = pq.ParquetFile(input_path)
    columns = ["catalog_id", "smiles", "parse_ok"]

    for batch in parquet_file.iter_batches(columns=columns):
        catalog_ids = batch.column("catalog_id")
        smiles_col = batch.column("smiles")
        parse_ok_col = batch.column("parse_ok")

        for i in range(batch.num_rows):
            if not parse_ok_col[i].as_py():
                continue

            catalog_id = catalog_ids[i].as_py()
            smiles = smiles_col[i].as_py()
            if catalog_id is None or smiles is None:
                continue

            yield (
                catalog_id,
                smiles,
                args.ph_min,
                args.ph_max,
                args.n_confs,
                args.keep_top_n,
                args.rmsd_prune_threshold,
                args.random_seed,
            )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Generate ranked, deduplicated multi-conformer PDBQT sets per "
            "candidate from a Parquet file of SMILES, packaged as an LMDB "
            "keyed by candidate id."
        )
    )
    p.add_argument("--input", required=True, type=Path, help="Input Parquet file.")
    p.add_argument("--output", required=True, type=Path, help="Output LMDB directory.")
    p.add_argument(
        "--map-size",
        type=int,
        default=1 << 33,  # 8 GiB
        help="LMDB map_size in bytes, i.e. the maximum size the environment "
        "may grow to (default: 8 GiB). LMDB reserves this address space "
        "up front but only uses what's written; oversize rather than "
        "undersize, since growing it later requires reopening the env.",
    )
    p.add_argument(
        "--n-confs",
        type=int,
        default=10,
        help="Number of conformers to embed per candidate before ranking/pruning \
              (default: 10).",
    )
    p.add_argument(
        "--keep-top-n",
        type=int,
        default=3,
        help="Number of conformers to retain per candidate after energy ranking and \
              RMSD pruning (default: 3).",
    )
    p.add_argument(
        "--rmsd-prune-threshold",
        type=float,
        default=0.5,
        help=(
            "Unaligned heavy-atom RMSD (Angstroms) below which a lower-ranked "
            "conformer is considered a near-duplicate of an already-kept one "
            "and dropped (default: 0.5)."
        ),
    )
    p.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue processing remaining candidates if some fail.",
    )
    p.add_argument(
        "--ph-min",
        type=float,
        default=6.4,
        help="Dimorphite-DL minimum pH (default: 6.4).",
    )
    p.add_argument(
        "--ph-max",
        type=float,
        default=8.4,
        help="Dimorphite-DL maximum pH (default: 8.4).",
    )
    p.add_argument(
        "--random-seed",
        type=int,
        default=1000,
        help="ETKDG random seed (default: 1000).",
    )
    p.add_argument(
        "--num-workers", metavar="N|auto", default="auto", type=_parse_num_workers
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return p.parse_args()


def prepare_ligands() -> int:
    args = _parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    args.output.mkdir(parents=True, exist_ok=True)
    env = lmdb.open(str(args.output), map_size=args.map_size)

    worker_args = _iter_candidate_args(args.input, args)

    n_ok = 0
    n_failed = 0
    pending: list[tuple[str, bytes]] = []

    def _flush(txn_pending: list[tuple[str, bytes]]) -> None:
        if not txn_pending:
            return
        with env.begin(write=True) as txn:
            for key, value in txn_pending:
                txn.put(key.encode("utf-8"), value)
        txn_pending.clear()

    try:
        with Pool(processes=args.num_workers) as pool:
            for candidate_id, packed, error in pool.imap_unordered(
                _worker_process_candidate, worker_args
            ):
                if error is not None:
                    n_failed += 1
                    logger.warning("candidate %s failed: %s", candidate_id, error)
                    if not args.skip_errors:
                        raise RuntimeError(f"candidate {candidate_id} failed: {error}")
                    continue

                pending.append((candidate_id, packed))
                n_ok += 1

                if len(pending) >= _LMDB_BATCH_SIZE:
                    logger.info("processed: %d", n_ok)
                    _flush(pending)

        _flush(pending)
    finally:
        env.close()

    logger.info("wrote %d candidates (%d failed) to %s", n_ok, n_failed, args.output)
    return 0 if n_failed == 0 or args.skip_errors else 1
