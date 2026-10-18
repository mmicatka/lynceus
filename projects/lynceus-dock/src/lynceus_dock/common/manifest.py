# projects/lynceus-dock/src/lynceus_dock/common/manifest.py

from __future__ import annotations

import json
import os
from pathlib import Path

MANIFEST_FILENAME = "docking_manifest.json"


def build_manifest_path(out_parquet: str) -> Path:
    return Path(out_parquet).parent / MANIFEST_FILENAME


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {"runs": {}}

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    if "runs" not in manifest:
        raise RuntimeError(
            f"Manifest at {manifest_path} is malformed: missing 'runs' key"
        )

    return manifest


def write_manifest(output_path: Path, manifest: dict) -> None:
    tmp_path = f"{output_path}.tmp"

    with open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp_path, output_path)


def run_key(member_id: str, site_id: str) -> str:
    return f"{member_id}::{site_id}"


def build_entry(
    member_id: str,
    site_id: str,
    ligands_path: str,
    ligand_row_count: int,
    out_parquet: str,
    pose_row_count: int,
) -> dict:
    return {
        "member_id": member_id,
        "site_id": site_id,
        "ligands_path": ligands_path,
        "ligand_row_count": ligand_row_count,
        "out_parquet": out_parquet,
        "pose_row_count": pose_row_count,
    }


def existing_entry_is_valid(
    entry: dict,
    ligands_path: str,
    ligand_row_count: int,
) -> bool:
    recorded_ligands_path = entry.get("ligands_path")
    recorded_row_count = entry.get("ligand_row_count")
    out_parquet = entry.get("out_parquet")

    if not recorded_ligands_path or recorded_row_count is None or not out_parquet:
        raise RuntimeError(
            "Manifest entry is missing 'ligands_path', 'ligand_row_count', "
            "or 'out_parquet', malformed entry, cannot trust as complete"
        )

    if recorded_ligands_path != ligands_path:
        raise RuntimeError(
            f"Manifest entry for member={entry.get('member_id')!r} "
            f"site={entry.get('site_id')!r} was recorded against "
            f"ligands_path={recorded_ligands_path!r} but this run passed "
            f"ligands_path={ligands_path!r}. Refusing to silently skip "
            f"or reprocess, resolve manually (e.g. delete the manifest "
            f"entry to force a redo)."
        )

    if recorded_row_count != ligand_row_count:
        raise RuntimeError(
            f"Manifest entry for member={entry.get('member_id')!r} "
            f"site={entry.get('site_id')!r} recorded "
            f"{recorded_row_count} ligand rows at {ligands_path!r} but "
            f"this run sees {ligand_row_count}. The file at that path "
            f"appears to have changed. Refusing to silently skip or "
            f"reprocess, resolve manually (e.g. delete the manifest "
            f"entry to force a redo)."
        )

    if not os.path.exists(out_parquet):
        raise RuntimeError(
            f"Manifest claims member={entry.get('member_id')!r} "
            f"site={entry.get('site_id')!r} is docked but output "
            f"{out_parquet} is missing, manifest is out of sync with "
            f"actual output. Refusing to silently reprocess; resolve "
            f"manually (e.g. delete the manifest entry to force a redo)."
        )

    return True
