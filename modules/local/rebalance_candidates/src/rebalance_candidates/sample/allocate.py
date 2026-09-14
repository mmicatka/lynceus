# modules/local/rebalance_candidates/src/rebalance_candidates/sample/allocate.py

import csv
import io
import json
import logging
import math

import click
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

from rebalance_candidates.sample.config import FolderAllocation, SamplingPlan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_path(path: str, use_blob_storage: bool, bucket: str) -> str:
    return f"s3://{bucket}/{path.lstrip('/')}" if use_blob_storage else path


def _read_json(input_path: str, use_blob_storage: bool, bucket: str) -> dict:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = _resolve_path(input_path, use_blob_storage, bucket)

    with fs.open(resolved_path, "r") as f:
        return json.load(f)


def _read_text(input_path: str, use_blob_storage: bool, bucket: str) -> str | None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = _resolve_path(input_path, use_blob_storage, bucket)

    if not fs.exists(resolved_path):
        return None

    with fs.open(resolved_path, "r") as f:
        content = f.read()

    if not isinstance(content, str):
        raise RuntimeError(f"Expected text content from {resolved_path}, got bytes")

    return content


def _write_text(
    output_path: str, content: str, use_blob_storage: bool, bucket: str
) -> None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = _resolve_path(output_path, use_blob_storage, bucket)

    with fs.open(resolved_path, "w") as f:
        f.write(content)

    logger.info("Wrote allocation manifest to %s", resolved_path)


def _parse_manifest(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def _manifest_matches_config(
    manifest_content: str,
    source_counts: dict[str, int],
    source_prefix: str,
    target_total: int,
    floor_per_source: int,
) -> bool:
    try:
        rows = _parse_manifest(manifest_content)
    except csv.Error:
        return False

    if not rows:
        return False

    expected_source_prefix = source_prefix.rstrip("/")
    manifest_folders = set()
    total_allocated = 0
    for row in rows:
        folder = row.get("folder")
        source = row.get("source")
        target_count_raw = row.get("target_count")
        if folder is None or source is None or target_count_raw is None:
            return False
        if source != f"{expected_source_prefix}/{folder}":
            return False
        if folder not in source_counts:
            return False
        try:
            target_count = int(target_count_raw)
        except ValueError:
            return False
        if target_count <= 0 or target_count > source_counts[folder]:
            return False
        manifest_folders.add(folder)
        total_allocated += target_count

    excluded_folders = {
        folder
        for folder, count in source_counts.items()
        if min(count, floor_per_source) == 0 and folder not in manifest_folders
    }
    expected_folders = set(source_counts) - excluded_folders
    if manifest_folders != expected_folders:
        return False

    return total_allocated <= target_total


def _allocate_candidate_samples(
    source_counts: dict[str, int],
    target_total: int,
    floor_per_source: int,
) -> SamplingPlan:
    if target_total <= 0:
        raise RuntimeError(f"target_total must be positive, got {target_total}")
    if floor_per_source < 0:
        raise RuntimeError(
            f"floor_per_folder must be non-negative, got {floor_per_source}"
        )

    floor_alloc = {
        folder: min(count, floor_per_source) for folder, count in source_counts.items()
    }
    floor_total = sum(floor_alloc.values())

    if floor_total > target_total:
        raise RuntimeError(
            f"floor_per_source={floor_per_source} across {len(source_counts)} sources "
            f"requires {floor_total} rows, exceeding target_total={target_total}"
        )

    remaining_budget = target_total - floor_total
    proportional_pool = {
        folder: count
        for folder, count in source_counts.items()
        if count > floor_per_source
    }
    pool_total = sum(proportional_pool.values())

    final_alloc = dict(floor_alloc)
    if pool_total > 0 and remaining_budget > 0:
        for folder, count in proportional_pool.items():
            additional = math.floor((count / pool_total) * remaining_budget)
            final_alloc[folder] = min(final_alloc[folder] + additional, count)

    allocations = [
        FolderAllocation(
            folder=folder,
            source_count=source_counts[folder],
            target_count=final_alloc[folder],
        )
        for folder in source_counts
    ]

    return SamplingPlan(
        target_total=target_total,
        floor_per_folder=floor_per_source,
        allocations=allocations,
    )


@click.command()
@click.option(
    "--candidate-counts",
    "counts_path",
    required=True,
    type=str,
    help="Path to JSON file mapping folder name to source compound count.",
)
@click.option(
    "--source-prefix",
    "source_prefix",
    required=True,
    type=str,
    help="Key prefix under which each folder lives, e.g. 'raw/zinc22'.",
)
@click.option(
    "--target-total",
    "target_total",
    required=True,
    type=int,
    help="Total number of compounds desired in the sampled POC dataset.",
)
@click.option(
    "--floor-per-source",
    "floor_per_source",
    required=True,
    type=int,
    help="Minimum number of compounds guaranteed per source.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output path for the allocation manifest (CSV: folder,source,target_count).",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read input and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def allocate_candidate_samples(
    counts_path: str,
    source_prefix: str,
    target_total: int,
    floor_per_source: int,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    source_counts_raw = _read_json(counts_path, use_blob_storage, bucket)
    if not source_counts_raw:
        raise RuntimeError(f"Candidate counts file is empty: {counts_path}")

    source_counts = {
        str(source): int(count) for source, count in source_counts_raw.items()
    }

    existing_manifest = _read_text(output_path, use_blob_storage, bucket)
    if existing_manifest is not None and _manifest_matches_config(
        existing_manifest, source_counts, source_prefix, target_total, floor_per_source
    ):
        logger.info(
            "%s already contains a valid allocation for the current config, skipping",
            output_path,
        )
        return

    plan = _allocate_candidate_samples(
        source_counts=source_counts,
        target_total=target_total,
        floor_per_source=floor_per_source,
    )

    total_allocated = sum(a.target_count for a in plan.allocations)
    logger.info(
        "Resolved allocation for %d folders: target_total=%d total_allocated=%d",
        len(plan.allocations),
        target_total,
        total_allocated,
    )

    lines = ["folder,source,target_count"]
    for allocation in plan.allocations:
        if allocation.target_count <= 0:
            logger.warning(
                "folder=%s resolved to target_count=0, excluding from manifest",
                allocation.folder,
            )
            continue
        source = f"{source_prefix.rstrip('/')}/{allocation.folder}"
        lines.append(f"{allocation.folder},{source},{allocation.target_count}")

    manifest_content = "\n".join(lines) + "\n"
    _write_text(output_path, manifest_content, use_blob_storage, bucket)
