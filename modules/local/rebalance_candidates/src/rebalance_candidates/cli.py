# modules/local/rebalance_candidates/src/rebalance_candidates/cli.py

import json
import logging
import re
from typing import Iterator, Sequence

import click
import fsspec
import pyarrow as pa
from lynceus_utils.duckdb import export_parquet, file_exists, get_connection
from lynceus_utils.storage import (
    get_blob_storage_settings,
    get_filesystem,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "rebalance_manifest.json"
SHARD_FILENAME_RE = re.compile(r"^shard_(\d+)\.parquet$")


def _parse_bool_skip_val(col: str, val: str) -> bool:
    normalized = val.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(
        f"--skip-col-val {col} {val!r}: value must be 'True' or 'False' "
        f"(case-insensitive) — skip-col-val only supports boolean columns"
    )


def _build_filtered_query(
    input_path: str, skip_col_vals: Sequence[tuple[str, str]]
) -> str:
    parsed = [(col, _parse_bool_skip_val(col, val)) for col, val in skip_col_vals]

    filter_conditions = [
        f"NOT COALESCE(CAST({col} AS BOOLEAN) = {bool_val}, FALSE)"
        for col, bool_val in parsed
    ]
    where_clause = (
        f"WHERE {' AND '.join(filter_conditions)}" if filter_conditions else ""
    )

    excluded_cols = list({col for col, _ in parsed})
    exclude_clause = f"EXCLUDE ({', '.join(excluded_cols)})" if excluded_cols else ""

    return f"""
        SELECT * {exclude_clause}
        FROM read_parquet('{input_path}')
        {where_clause}
    """


def _generate_sharded_tables(
    reader: pa.RecordBatchReader, num_per_shard: int
) -> Iterator[pa.Table]:
    current_batches: list[pa.RecordBatch] = []
    current_rows = 0

    for batch in reader:
        current_batches.append(batch)
        current_rows += batch.num_rows

        while current_rows >= num_per_shard:
            table = pa.Table.from_batches(current_batches)
            shard_table = table.slice(0, num_per_shard)
            remainder_table = table.slice(num_per_shard)

            yield shard_table

            if remainder_table.num_rows > 0:
                current_batches = remainder_table.to_batches()
                current_rows = remainder_table.num_rows
            else:
                current_batches = []
                current_rows = 0

    if current_rows > 0:
        yield pa.Table.from_batches(current_batches)


def _manifest_path(target_dir: str) -> str:
    return f"{target_dir}/{MANIFEST_FILENAME}"


def _load_manifest(fs: fsspec.AbstractFileSystem, manifest_path: str) -> dict:
    if not fs.exists(manifest_path):
        return {"globs": {}}

    with fs.open(manifest_path, "r") as f:
        manifest = json.load(f)

    if "globs" not in manifest:
        raise RuntimeError(
            f"Manifest at {manifest_path} is malformed: missing 'globs' key"
        )

    return manifest


def _write_manifest(
    fs: fsspec.AbstractFileSystem, manifest_path: str, manifest: dict
) -> None:
    tmp_path = f"{manifest_path}.tmp"

    with fs.open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    fs.mv(tmp_path, manifest_path)


def _list_shard_indices(
    fs: fsspec.AbstractFileSystem, target_dir: str
) -> dict[int, str]:
    indices: dict[int, str] = {}
    for entry_path in fs.ls(target_dir, detail=False):
        filename = entry_path.rsplit("/", 1)[-1]
        match = SHARD_FILENAME_RE.match(filename)
        if match:
            indices[int(match.group(1))] = filename

    return indices


def _all_manifest_shard_filenames(manifest: dict) -> set[str]:
    filenames: set[str] = set()
    for entry in manifest["globs"].values():
        filenames.update(entry["shard_files"])
    return filenames


def _next_shard_counter(fs, target_dir: str, manifest: dict) -> int:
    on_disk = _list_shard_indices(fs, target_dir)
    known = _all_manifest_shard_filenames(manifest)

    orphans = {filename for filename in on_disk.values() if filename not in known}
    if orphans:
        raise RuntimeError(
            f"Found shard file(s) in {target_dir} not referenced by any "
            f"manifest entry: {sorted(orphans)}. This indicates a crashed "
            f"or partial prior run. Refusing to proceed silently — "
            f"resolve manually (delete orphans or repair the manifest) "
            f"before rerunning."
        )

    return max(on_disk.keys(), default=-1) + 1


def _matched_input_files(con, input_path: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT filename FROM read_parquet(?, filename=true)",
        [input_path],
    ).fetchall()
    return sorted(row[0] for row in rows)


def _existing_entry_is_valid(
    con, entry: dict, target_dir: str, matched_files: list[str]
) -> bool:
    recorded_files = entry.get("matched_files")
    shard_files = entry.get("shard_files")

    if not recorded_files or not shard_files:
        raise RuntimeError(
            "Manifest entry is missing 'matched_files' or 'shard_files' — "
            "malformed entry, cannot trust as complete"
        )

    if sorted(recorded_files) != matched_files:
        added = sorted(set(matched_files) - set(recorded_files))
        removed = sorted(set(recorded_files) - set(matched_files))
        raise RuntimeError(
            f"Glob '{entry['input_glob']}' now matches a different file "
            f"set than when it was rebalanced. Added: {added}. "
            f"Removed: {removed}. Refusing to silently skip or reprocess "
            f"— resolve manually (e.g. delete the manifest entry to force "
            f"a redo, or narrow the glob to exclude the new files)."
        )

    for shard_file in shard_files:
        shard_path = f"{target_dir}/{shard_file}"
        if not file_exists(con, shard_path):
            raise RuntimeError(
                f"Manifest claims glob '{entry['input_glob']}' is "
                f"rebalanced but shard {shard_path} is missing or "
                f"unreadable — manifest is out of sync with actual "
                f"output. Refusing to silently reprocess; resolve "
                f"manually (e.g. delete the manifest entry to force a "
                f"redo)."
            )

    return True


def _rebalance_glob(
    con,
    input_path: str,
    matched_files: list[str],
    target_dir: str,
    num_per_shard: int,
    skip_col_val: Sequence[tuple[str, str]],
    shard_counter_start: int,
) -> dict:
    query = _build_filtered_query(input_path, skip_col_val)
    reader = con.execute(query).fetch_record_batch()

    shard_files: list[str] = []
    shard_idx = shard_counter_start
    for shard_table in _generate_sharded_tables(reader, num_per_shard):
        shard_file = f"shard_{shard_idx}.parquet"
        shard_path = f"{target_dir}/{shard_file}"

        if file_exists(con, shard_path):
            raise RuntimeError(
                f"Refusing to overwrite existing shard {shard_path}. "
                f"This should be unreachable given the counter scan — "
                f"investigate a possible race with another concurrent run."
            )

        export_parquet(con, shard_table, shard_path)
        shard_files.append(shard_file)
        shard_idx += 1

    return {
        "input_glob": input_path,
        "matched_files": matched_files,
        "shard_files": shard_files,
        "shard_count": len(shard_files),
    }


@click.command()
@click.option("--input", type=str, required=True, help="Input path (glob).")
@click.option("--output", type=str, required=True, help="Output path.")
@click.option(
    "--num-per-shard",
    default=10000,
    type=int,
    show_default=True,
    help="Number of candidates per shard.",
)
@click.option(
    "--skip-col-val",
    type=(str, str),
    multiple=True,
    help="Column and value pair to skip (e.g. --skip-col-val steps_ok False)."
    " Can be passed multiple times.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output Parquet file to blob storage.",
)
@click.option("--bucket", type=str, default="lynceus", help="Output bucket name")
def rebalance_candidates(
    input: str,
    output: str,
    num_per_shard: int,
    skip_col_val: list[tuple[str, str]],
    use_blob_storage: bool,
    bucket: str,
):
    blob_storage_settings = None

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        target_dir = f"s3://{bucket}/{output.lstrip('/')}"
    else:
        target_dir = output.rstrip("/")

    conn = get_connection(blob_storage_settings)
    fs = get_filesystem(blob_storage_settings)

    manifest_path = _manifest_path(target_dir)
    manifest = _load_manifest(fs, manifest_path)

    matched_files = _matched_input_files(conn, input)
    if not matched_files:
        raise RuntimeError(
            f"Glob '{input}' matched no files — refusing to write an "
            f"empty manifest entry."
        )

    existing_entry = manifest["globs"].get(input)
    if existing_entry is not None:
        _existing_entry_is_valid(conn, existing_entry, target_dir, matched_files)
        logger.info(
            f"Skipping '{input}': already rebalanced "
            f"({existing_entry['shard_count']} shards verified present, "
            f"{len(matched_files)} matched files unchanged)"
        )
        return

    shard_counter_start = _next_shard_counter(fs, target_dir, manifest)

    logger.info(
        f"Reading from '{input}' ({len(matched_files)} files matched) "
        f"with {num_per_shard} rows per file, starting at shard_{shard_counter_start}"
    )

    entry = _rebalance_glob(
        conn,
        input,
        matched_files,
        target_dir,
        num_per_shard,
        skip_col_val,
        shard_counter_start,
    )

    manifest["globs"][input] = entry
    _write_manifest(fs, manifest_path, manifest)

    logger.info(
        f"Successfully wrote {entry['shard_count']} shards to {target_dir} "
        f"and updated manifest at {manifest_path}"
    )
