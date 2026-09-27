# modules/local/rebalance_candidates/src/rebalance_candidates/count/merge.py

import json
import logging

import click
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

from rebalance_candidates.count.count import _read_json, _resolve_path, _write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _resolve_glob_paths(fs, pattern: str) -> list[str]:
    matches = fs.glob(pattern)
    if isinstance(matches, dict):
        return list(matches.keys())
    return [str(path) for path in matches]


def _load_entries(count_paths: list[str], fs) -> dict[str, int]:
    merged: dict[str, int] = {}
    for path in count_paths:
        with fs.open(path, "r") as f:
            entry = json.load(f)
        folder = entry["folder"]
        count = entry["count"]
        if folder in merged:
            raise RuntimeError(
                f"Duplicate folder={folder} encountered while merging counts"
            )
        merged[folder] = count
    return merged


@click.command()
@click.option(
    "--input",
    "parquet_prefix",
    required=True,
    type=str,
    help="Parquet output prefix containing one subfolder per source,"
    " each with a count.json",
)
@click.option(
    "--output",
    required=True,
    type=str,
    help="Output path for the merged candidate count JSON.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read source and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def merge_candidate_counts(
    parquet_prefix: str,
    output: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    glob_pattern = _resolve_path(
        f"{parquet_prefix.rstrip('/')}/*/count.json", use_blob_storage, bucket
    )
    count_paths = _resolve_glob_paths(fs, glob_pattern)

    if not count_paths:
        raise RuntimeError(f"No count.json files found at {glob_pattern}")

    merged = _load_entries(count_paths, fs)

    existing = _read_json(output, use_blob_storage, bucket)
    if existing is not None and existing == merged:
        logger.info(
            "%s already contains merged counts for all %d folders, skipping",
            output,
            len(merged),
        )
        return

    logger.info("Merged counts for %d candidate sources", len(merged))
    _write_json(output, merged, use_blob_storage, bucket)
