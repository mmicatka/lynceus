# modules/local/rebalance_candidates/src/rebalance_candidates/sample/allocate.py

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


def _read_json(input_path: str, use_blob_storage: bool, bucket: str) -> dict:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = (
        f"s3://{bucket}/{input_path.lstrip('/')}" if use_blob_storage else input_path
    )

    with fs.open(resolved_path, "r") as f:
        return json.load(f)


def _write_text(
    output_path: str, content: str, use_blob_storage: bool, bucket: str
) -> None:
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)
    resolved_path = (
        f"s3://{bucket}/{output_path.lstrip('/')}" if use_blob_storage else output_path
    )

    with fs.open(resolved_path, "w") as f:
        f.write(content)

    logger.info("Wrote allocation manifest to %s", resolved_path)


def _allocate_candidate_samples(
    folder_counts: dict[str, int],
    target_total: int,
    floor_per_folder: int,
) -> SamplingPlan:
    if target_total <= 0:
        raise RuntimeError(f"target_total must be positive, got {target_total}")
    if floor_per_folder < 0:
        raise RuntimeError(
            f"floor_per_folder must be non-negative, got {floor_per_folder}"
        )

    floor_alloc = {
        folder: min(count, floor_per_folder) for folder, count in folder_counts.items()
    }
    floor_total = sum(floor_alloc.values())

    if floor_total > target_total:
        raise RuntimeError(
            f"floor_per_folder={floor_per_folder} across {len(folder_counts)} folders "
            f"requires {floor_total} rows, exceeding target_total={target_total}"
        )

    remaining_budget = target_total - floor_total
    proportional_pool = {
        folder: count
        for folder, count in folder_counts.items()
        if count > floor_per_folder
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
            source_count=folder_counts[folder],
            target_count=final_alloc[folder],
        )
        for folder in folder_counts
    ]

    return SamplingPlan(
        target_total=target_total,
        floor_per_folder=floor_per_folder,
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
    "--floor-per-folder",
    "floor_per_folder",
    required=True,
    type=int,
    help="Minimum number of compounds guaranteed per folder.",
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
    floor_per_folder: int,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    folder_counts_raw = _read_json(counts_path, use_blob_storage, bucket)
    if not folder_counts_raw:
        raise RuntimeError(f"Candidate counts file is empty: {counts_path}")

    folder_counts = {
        str(folder): int(count) for folder, count in folder_counts_raw.items()
    }

    plan = _allocate_candidate_samples(
        folder_counts=folder_counts,
        target_total=target_total,
        floor_per_folder=floor_per_folder,
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
