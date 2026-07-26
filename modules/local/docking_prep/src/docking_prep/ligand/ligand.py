# modules/local/docking_prep/src/docking_prep/ligand/ligand.py

from __future__ import annotations

import argparse
import logging
import math
import multiprocessing
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import blake3
from docking_prep.ligand.models import (
    CandidateResult,
    ConformerRecord,
    EmbeddedConformer,
)
import pandas as pd
import yaml
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.rdchem import Mol
import dimorphite_dl


logger = logging.getLogger("generate_conformers")


def select_protonation_state(
    smiles: str,
    ph_min: float = 6.4,
    ph_max: float = 8.4,
) -> str:
    variants = dimorphite_dl.protonate_smiles(
        smiles, ph_min=ph_min, ph_max=ph_max, validate_output=True
    )
    if not variants:
        raise ValueError(
            f"Dimorphite-DL returned no protonation states for SMILES: {smiles!r}"
        )

    def sort_key(variant_smiles: str) -> tuple[int, str]:
        mol = Chem.MolFromSmiles(variant_smiles)
        if mol is None:
            return (10**6, variant_smiles)
        formal_charge = Chem.GetFormalCharge(mol)
        canonical = Chem.MolToSmiles(mol)
        return (abs(formal_charge), canonical)

    return min(variants, key=sort_key)


def embed_and_rank_conformers(
    smiles: str,
    n_confs: int,
    random_seed: int = 1000,
    max_iters: int = 500,
) -> tuple[Mol, list[EmbeddedConformer]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed
    params.useRandomCoords = True
    params.pruneRmsThresh = -1.0  # no built-in pruning; we prune explicitly later

    conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=n_confs, params=params))
    if not conf_ids:
        raise ValueError(f"RDKit ETKDG embedding failed for SMILES: {smiles!r}")

    mmff_props = AllChem.MMFFGetMoleculeProperties(mol)
    if mmff_props is None:
        raise ValueError(
            f"MMFF94 parameters unavailable for SMILES: {smiles!r} "
            "(unsupported atom types for MMFF)"
        )

    embedded: list[EmbeddedConformer] = []
    for conf_id in conf_ids:
        ff = AllChem.MMFFGetMoleculeForceField(mol, mmff_props, confId=conf_id)
        if ff is None:
            logger.warning(
                "Could not construct MMFF94 force field for conformer %d of %r; dropping it.",
                conf_id,
                smiles,
            )
            continue
        converged = ff.Minimize(maxIts=max_iters)
        if converged != 0:
            logger.warning(
                "MMFF94 minimization did not fully converge within %d iterations "
                "for conformer %d of %r; keeping best available geometry.",
                max_iters,
                conf_id,
                smiles,
            )
        energy = ff.CalcEnergy()
        embedded.append(EmbeddedConformer(conf_id=conf_id, mmff_energy=energy))

    embedded.sort(key=lambda e: e.mmff_energy)
    return mol, embedded


def _unaligned_rmsd(
    mol: Mol, conf_id_1: int, conf_id_2: int, heavy_atom_only: bool = True
) -> float:
    """Plain coordinate-wise RMSD between two conformers of the SAME
    molecule object, with NO alignment step.

    This is only valid because both conformers share identical atom
    ordering (they come from repeated EmbedMultipleConfs calls on one Mol),
    so index i always refers to the same atom in both conformers. It is a
    fast near-duplicate filter, not a rigorous shape-similarity metric —
    two conformers that are true rigid-body rotations/translations of each
    other but happen to have been embedded in different orientations will
    NOT be recognized as duplicates by this check. That's an accepted
    simplification for pruning near-identical embeddings from the same
    ETKDG run, not a general conformer-clustering method.

    Deliberately does not use RDKit's AllChem.GetConformerRMS: empirically,
    that function's `prealigned` flag does not actually disable its
    internal alignment step (verified: RMSD was identical whether
    prealigned=True or False, even after manually translating one
    conformer by 50 Angstroms), so it cannot produce a genuinely unaligned
    RMSD regardless of which value is passed.
    """
    c1 = mol.GetConformer(conf_id_1)
    c2 = mol.GetConformer(conf_id_2)
    sq_diffs = []
    for atom in mol.GetAtoms():
        if heavy_atom_only and atom.GetAtomicNum() == 1:
            continue
        i = atom.GetIdx()
        p1, p2 = c1.GetAtomPosition(i), c2.GetAtomPosition(i)
        sq_diffs.append((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)
    if not sq_diffs:
        return 0.0
    return math.sqrt(sum(sq_diffs) / len(sq_diffs))


def prune_and_select_top_n(
    mol: Mol,
    embedded: list[EmbeddedConformer],
    keep_top_n: int,
    rmsd_prune_threshold: float,
) -> list[EmbeddedConformer]:
    """Greedily walk `embedded` in ascending-energy order, keeping a
    conformer only if it's not within `rmsd_prune_threshold` Angstroms
    (unaligned heavy-atom RMSD) of any already-kept conformer. Stops once
    keep_top_n conformers are retained.
    """
    kept: list[EmbeddedConformer] = []
    for candidate in embedded:
        if len(kept) >= keep_top_n:
            break
        is_duplicate = any(
            _unaligned_rmsd(mol, candidate.conf_id, k.conf_id) < rmsd_prune_threshold
            for k in kept
        )
        if not is_duplicate:
            kept.append(candidate)
    return kept


def conformer_to_pdbqt(mol: Mol, conf_id: int, name: str) -> str:
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    mol.SetProp("_Name", name)
    preparator = MoleculePreparation()
    setups = preparator.prepare(mol, conformer_id=conf_id)
    if not setups:
        raise ValueError("Meeko produced no molecule setups for this conformer")

    setup = setups[0]
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setup)
    if not is_ok:
        raise ValueError(f"Meeko PDBQT writing failed: {error_msg}")
    return pdbqt_string


def content_id(data: bytes, length: int = 16) -> str:
    return blake3.blake3(data).hexdigest(length // 2)


def content_hash(data: bytes) -> str:
    return f"blake3:{blake3.blake3(data).hexdigest()}"


def process_candidate(
    candidate_id: str,
    smiles: str,
    ph_min: float,
    ph_max: float,
    n_confs: int,
    keep_top_n: int,
    rmsd_prune_threshold: float,
    random_seed: int,
) -> CandidateResult:
    try:
        protonated_smiles = select_protonation_state(
            smiles, ph_min=ph_min, ph_max=ph_max
        )
        mol, embedded = embed_and_rank_conformers(
            protonated_smiles, n_confs=n_confs, random_seed=random_seed
        )
        kept = prune_and_select_top_n(mol, embedded, keep_top_n, rmsd_prune_threshold)

        conformers: list[ConformerRecord] = []
        for rank, e in enumerate(kept):
            pdbqt_text = conformer_to_pdbqt(
                mol, e.conf_id, name=f"{candidate_id}_rank{rank}"
            )
            cid = content_id(pdbqt_text.encode("utf-8"))
            conformers.append(
                ConformerRecord(
                    conformer_id=cid,
                    pdbqt_text=pdbqt_text,
                    mmff_energy=e.mmff_energy,
                    rank=rank,
                )
            )

        return CandidateResult(
            candidate_id=candidate_id,
            source_smiles=smiles,
            protonated_smiles=protonated_smiles,
            conformers=conformers,
            n_confs_requested=n_confs,
            n_confs_embedded=len(embedded),
            random_seed=random_seed,
            ph_min=ph_min,
            ph_max=ph_max,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - intentionally broad: isolate per-candidate failures
        return CandidateResult(
            candidate_id=candidate_id,
            source_smiles=smiles,
            protonated_smiles=None,
            error=str(exc),
        )


def _process_candidate_star(args: tuple) -> CandidateResult:
    """Module-level, picklable wrapper for multiprocessing.Pool.imap, which
    only maps over a single iterable argument.
    """
    return process_candidate(*args)


def process_candidates_parallel(
    rows: list[tuple[str, str]],
    ph_min: float,
    ph_max: float,
    n_confs: int,
    keep_top_n: int,
    rmsd_prune_threshold: float,
    random_seed: int,
    n_workers: int,
) -> list[CandidateResult]:
    tasks = [
        (
            cid,
            smi,
            ph_min,
            ph_max,
            n_confs,
            keep_top_n,
            rmsd_prune_threshold,
            random_seed,
        )
        for cid, smi in rows
    ]
    if n_workers <= 1:
        return [process_candidate(*t) for t in tasks]

    with multiprocessing.Pool(processes=n_workers) as pool:
        return list(pool.imap(_process_candidate_star, tasks))


def build_manifest(result: CandidateResult, source_tool: str) -> dict:
    """Build the conformer-manifest.yaml contents for one candidate."""
    conformer_files_bytes = b"".join(
        c.pdbqt_text.encode("utf-8") for c in result.conformers
    )
    return {
        "schema_version": "1.0.0",
        "candidate_id": result.candidate_id,
        "source_smiles": result.source_smiles,
        "protonated_smiles": result.protonated_smiles,
        "protonation": {
            "tool": source_tool,
            "ph_min": result.ph_min,
            "ph_max": result.ph_max,
        },
        "generation": {
            "n_confs_requested": result.n_confs_requested,
            "n_confs_embedded": result.n_confs_embedded,
            "n_confs_retained": len(result.conformers),
            "random_seed": result.random_seed,
        },
        "conformers": [
            {
                "id": c.conformer_id,
                "file": f"{c.conformer_id}.pdbqt",
                "mmff_energy": round(c.mmff_energy, 4),
                "rank": c.rank,
            }
            for c in result.conformers
        ],
        "content_hash": content_hash(conformer_files_bytes),
    }


def sanitize_dirname(candidate_id: str) -> str:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in candidate_id)
    return safe or "unnamed_candidate"


def write_candidate_directory(
    result: CandidateResult, out_root: Path, source_tool: str
) -> None:
    candidate_dir = out_root / sanitize_dirname(result.candidate_id)
    candidate_dir.mkdir(parents=True, exist_ok=True)

    for c in result.conformers:
        (candidate_dir / f"{c.conformer_id}.pdbqt").write_text(c.pdbqt_text)

    manifest = build_manifest(result, source_tool=source_tool)
    with open(candidate_dir / "conformer-manifest.yaml", "w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, default_flow_style=False)


def make_tarball(source_dir: Path, output_path: Path) -> None:
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)


def load_candidates(
    parquet_path: Path, id_column: str, smiles_column: str
) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path, columns=[id_column, smiles_column])

    missing_cols = {id_column, smiles_column} - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Input parquet is missing required column(s): {sorted(missing_cols)}"
        )

    n_total = len(df)
    df = df.dropna(subset=[id_column, smiles_column])
    n_dropped_na = n_total - len(df)
    if n_dropped_na:
        logger.warning("Dropped %d row(s) with null id/SMILES.", n_dropped_na)

    df[id_column] = df[id_column].astype(str)
    duplicated = df[id_column].duplicated(keep=False)
    if duplicated.any():
        dup_ids = sorted(df.loc[duplicated, id_column].unique())
        raise ValueError(
            f"Duplicate candidate IDs found in column {id_column!r}: {dup_ids[:10]}"
            + (" ... (truncated)" if len(dup_ids) > 10 else "")
        )

    if df.empty:
        raise ValueError("No valid candidate rows remain after dropping nulls.")

    return df.reset_index(drop=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate ranked, deduplicated multi-conformer PDBQT sets per "
            "candidate from a Parquet file of SMILES, packaged as a tar.gz "
            "of <candidate-id>/conformer-manifest.yaml + <conformer-id>.pdbqt."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Input Parquet file.")
    parser.add_argument(
        "--output", required=True, type=Path, help="Output tar.gz path."
    )
    parser.add_argument(
        "--id-column", required=True, help="Column name containing candidate IDs."
    )
    parser.add_argument(
        "--smiles-column",
        default="smiles",
        help="Column name containing SMILES (default: smiles).",
    )
    parser.add_argument(
        "--n-confs",
        type=int,
        default=10,
        help="Number of conformers to embed per candidate before ranking/pruning (default: 10).",
    )
    parser.add_argument(
        "--keep-top-n",
        type=int,
        default=3,
        help="Number of conformers to retain per candidate after energy ranking and RMSD pruning (default: 3).",
    )
    parser.add_argument(
        "--rmsd-prune-threshold",
        type=float,
        default=0.5,
        help=(
            "Unaligned heavy-atom RMSD (Angstroms) below which a lower-ranked "
            "conformer is considered a near-duplicate of an already-kept one "
            "and dropped (default: 0.5)."
        ),
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue processing remaining candidates if some fail, instead of exiting non-zero.",
    )
    parser.add_argument(
        "--ph-min",
        type=float,
        default=6.4,
        help="Dimorphite-DL minimum pH (default: 6.4).",
    )
    parser.add_argument(
        "--ph-max",
        type=float,
        default=8.4,
        help="Dimorphite-DL maximum pH (default: 8.4).",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=0xF00D,
        help="ETKDG random seed (default: 0xF00D).",
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=1,
        help="Number of worker processes for parallel candidate processing (default: 1, sequential).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 1

    if args.n_workers < 1:
        logger.error("--n-workers must be >= 1, got %d", args.n_workers)
        return 1

    if args.keep_top_n < 1:
        logger.error("--keep-top-n must be >= 1, got %d", args.keep_top_n)
        return 1

    if args.n_confs < args.keep_top_n:
        logger.warning(
            "--n-confs (%d) is less than --keep-top-n (%d); at most %d conformer(s) "
            "will be retained per candidate.",
            args.n_confs,
            args.keep_top_n,
            args.n_confs,
        )

    try:
        df = load_candidates(args.input, args.id_column, args.smiles_column)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("Loaded %d candidate(s) from %s", len(df), args.input)

    rows = list(zip(df[args.id_column], df[args.smiles_column]))
    logger.info(
        "Processing %d candidate(s) with %d worker(s)...", len(rows), args.n_workers
    )
    results = process_candidates_parallel(
        rows,
        ph_min=args.ph_min,
        ph_max=args.ph_max,
        n_confs=args.n_confs,
        keep_top_n=args.keep_top_n,
        rmsd_prune_threshold=args.rmsd_prune_threshold,
        random_seed=args.random_seed,
        n_workers=args.n_workers,
    )

    n_success = 0
    n_failed = 0
    with TemporaryDirectory(prefix="conformers_") as tmp:
        out_root = Path(tmp) / args.output.name.removesuffix(".tar.gz").removesuffix(
            ".tgz"
        )
        out_root.mkdir(parents=True, exist_ok=True)

        for result in results:
            if not result.ok:
                n_failed += 1
                logger.error(
                    "Failed candidate %r: %s", result.candidate_id, result.error
                )
                continue
            if not result.conformers:
                n_failed += 1
                logger.error(
                    "Candidate %r produced zero usable conformers after embedding/pruning.",
                    result.candidate_id,
                )
                continue
            write_candidate_directory(
                result, out_root, source_tool="lynceus_dimorphite_dl"
            )
            n_success += 1

        if n_success == 0:
            logger.error("All %d candidate(s) failed; no output written.", n_failed)
            return 1

        args.output.parent.mkdir(parents=True, exist_ok=True)
        make_tarball(out_root, args.output)

    logger.info(
        "Done: %d succeeded, %d failed. Archive written to %s",
        n_success,
        n_failed,
        args.output,
    )

    if n_failed and not args.skip_errors:
        logger.error(
            "%d candidate(s) failed and --skip-errors was not set; exiting non-zero.",
            n_failed,
        )
        return 1

    return 0
