# modules/local/sample_candidates/src/sample_candidates/manifest.py

from __future__ import annotations

import json

import fsspec
from lynceus_utils.duckdb import file_exists

from sample_candidates.config import StratificationConfig

MANIFEST_FILENAME = "sample_manifest.json"


def manifest_path(output: str) -> str:
    parent_dir = output.rsplit("/", 1)[0] if "/" in output else "."
    return f"{parent_dir}/{MANIFEST_FILENAME}"


def load_manifest(fs: fsspec.AbstractFileSystem, path: str) -> dict:
    if not fs.exists(path):
        return {"globs": {}}

    with fs.open(path, "r") as f:
        manifest = json.load(f)

    if "globs" not in manifest:
        raise RuntimeError(f"Manifest at {path} is malformed: missing 'globs' key")

    return manifest


def write_manifest(fs: fsspec.AbstractFileSystem, path: str, manifest: dict) -> None:
    tmp_path = f"{path}.tmp"

    with fs.open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    fs.mv(tmp_path, path)


def serialize_params(config: StratificationConfig, cap_per_stratum: int | None) -> dict:
    return {
        "features": [f.model_dump(mode="json") for f in config.features],
        "n_projected_dims": config.n_projected_dims,
        "projection_density": config.projection_density,
        "random_seed": config.random_seed,
        "n_quantiles_per_dim": config.n_quantiles_per_dim,
        "cap_per_stratum": cap_per_stratum,
        "target_total_samples": config.target_total_samples,
        "min_stratum_size_for_cap": config.min_stratum_size_for_cap,
    }


def build_entry(
    input_path: str,
    matched_files: list[str],
    output: str,
    params: dict,
    row_count: int,
    n_strata: int,
) -> dict:
    return {
        "input_glob": input_path,
        "matched_files": matched_files,
        "output": output,
        "params": params,
        "row_count": row_count,
        "n_strata": n_strata,
    }


def existing_entry_is_valid(
    con, entry: dict, matched_files: list[str], params: dict
) -> bool:
    recorded_files = entry.get("matched_files")
    recorded_params = entry.get("params")
    output = entry.get("output")

    if not recorded_files or recorded_params is None or not output:
        raise RuntimeError(
            "Manifest entry is missing 'matched_files', 'params', or 'output'"
        )

    if sorted(recorded_files) != sorted(matched_files):
        added = sorted(set(matched_files) - set(recorded_files))
        removed = sorted(set(recorded_files) - set(matched_files))
        raise RuntimeError(
            f"Glob '{entry['input_glob']}' now matches a different file "
            f"set than when it was sampled. Added: {added}. "
            f"Removed: {removed}."
        )

    if recorded_params != params:
        raise RuntimeError(
            f"Glob '{entry['input_glob']}' was previously sampled with "
            f"different parameters. Recorded: {recorded_params}. "
            f"Requested: {params}."
        )

    if not file_exists(con, output):
        raise RuntimeError(
            f"Manifest claims glob '{entry['input_glob']}' is sampled "
            f"but output {output} is missing or unreadable"
        )

    return True
