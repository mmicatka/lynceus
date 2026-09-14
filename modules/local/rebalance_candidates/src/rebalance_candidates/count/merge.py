# modules/local/rebalance_candidates/src/rebalance_candidates/count/merge.py

import json
import logging

import click
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

from rebalance_candidates.count.count import _read_json, _write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _load_entries(
    keys: list[str], use_blob_storage: bool, bucket: str, fs
) -> dict[str, int]:
    merged: dict[str, int] = {}
    for key in keys:
        resolved_key = f"s3://{bucket}/{key.lstrip('/')}" if use_blob_storage else key
        with fs.open(resolved_key, "r") as f:
            entry = json.load(f)
        folder = entry["folder"]
        count = entry["count"]
        if folder in merged:
            raise RuntimeError(
                f"Duplicate folder={folder} encountered while merging counts"
            )
        merged[folder] = count
    return merged


def _expected_folders(keys: list[str]) -> set[str]:
    folders = set()
    for key in keys:
        filename = key.rstrip("/").split("/")[-1]
        if not filename.endswith("_count.json"):
            raise RuntimeError(
                f"key={key} does not match expected *_count.json pattern"
            )
        folders.add(filename[: -len("_count.json")])
    return folders


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input folder",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output path for the candidate count JSON.",
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
    input_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    keys = [k for k in input_path.split(",") if k]
    if not keys:
        raise RuntimeError("No candidate count keys provided to merge")

    expected_folders = _expected_folders(keys)

    existing = _read_json(output_path, use_blob_storage, bucket)
    if existing is not None and set(existing.keys()) == expected_folders:
        logger.info(
            "%s already contains merged counts for all %d folders, skipping",
            output_path,
            len(expected_folders),
        )
        return

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    merged = _load_entries(keys, use_blob_storage, bucket, fs)

    logger.info("Merged counts for %d candidate sources", len(merged))
    _write_json(output_path, merged, use_blob_storage, bucket)
