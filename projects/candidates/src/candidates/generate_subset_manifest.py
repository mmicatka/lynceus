# projects/candidates/src/candidates/generate_subset_manifest.py

import csv
import glob
import io
import math
import os
import sys

import click
import pyarrow.parquet as pq
import structlog
from lynceus_core.logging import wide_log

from candidates.config import FolderAllocation, SubsetPlan


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()


def _read_text(input_path: str) -> str | None:
    if not os.path.exists(input_path):
        return None

    with open(input_path, "r") as f:
        return f.read()


def _write_text(output_path: str, content: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(content)

    logger.info("Wrote allocation manifest", path=output_path)


def _get_folder_row_counts(source_dir: str) -> dict[str, int]:
    counts = {}

    if not os.path.exists(source_dir):
        raise RuntimeError(f"Source directory does not exist: {source_dir}")

    for folder in os.listdir(source_dir):
        folder_path = os.path.join(source_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        total_rows = 0
        parquet_files = glob.glob(os.path.join(folder_path, "*.parquet"))

        for pq_file in parquet_files:
            with open(pq_file, "rb") as f:
                total_rows += pq.ParquetFile(f).metadata.num_rows

        if total_rows > 0:
            counts[folder] = total_rows

    return counts


def _parse_manifest(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def _manifest_matches_config(
    manifest_content: str,
    source_counts: dict[str, int],
    source_dir: str,
    target_total: int,
    min_per_source: int,
) -> bool:
    try:
        rows = _parse_manifest(manifest_content)
    except csv.Error:
        return False

    if not rows:
        return False

    expected_source_dir = source_dir.rstrip("/")
    manifest_folders = set()
    total_allocated = 0
    for row in rows:
        folder = row.get("folder")
        source = row.get("source")
        target_count_raw = row.get("target_count")
        source_count_raw = row.get("source_count")

        if (
            folder is None
            or source is None
            or target_count_raw is None
            or source_count_raw is None
        ):
            return False

        if source != f"{expected_source_dir}/{folder}":
            return False

        if folder not in source_counts:
            return False

        try:
            target_count = int(target_count_raw)
            source_count = int(source_count_raw)
        except ValueError:
            return False

        if source_count != source_counts[folder]:
            return False

        if target_count <= 0 or target_count > source_counts[folder]:
            return False

        manifest_folders.add(folder)
        total_allocated += target_count

    excluded_folders = {
        folder
        for folder, count in source_counts.items()
        if min(count, min_per_source) == 0 and folder not in manifest_folders
    }
    expected_folders = set(source_counts) - excluded_folders
    if manifest_folders != expected_folders:
        return False

    return total_allocated <= target_total


def _allocate_candidate_subset(
    source_counts: dict[str, int],
    target_total: int,
    min_per_source: int,
) -> SubsetPlan:
    if target_total <= 0:
        raise RuntimeError(f"target_total must be positive, got {target_total}")
    if min_per_source < 0:
        raise RuntimeError(f"min_per_folder must be non-negative, got {min_per_source}")

    min_alloc = {
        folder: min(count, min_per_source) for folder, count in source_counts.items()
    }
    min_total = sum(min_alloc.values())

    if min_total > target_total:
        raise RuntimeError(
            f"min_per_source={min_per_source} across {len(source_counts)} sources "
            f"requires {min_total} rows, exceeding target_total={target_total}"
        )

    remaining_budget = target_total - min_total
    proportional_pool = {
        folder: count
        for folder, count in source_counts.items()
        if count > min_per_source
    }
    pool_total = sum(proportional_pool.values())

    final_alloc = dict(min_alloc)
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

    return SubsetPlan(
        target_total=target_total,
        min_per_folder=min_per_source,
        allocations=allocations,
    )


@click.command()
@click.option(
    "--source-dir",
    "source_dir",
    required=True,
    type=str,
    help="Path to the directory containing candidate folders of Parquet files.",
)
@click.option(
    "--target-total",
    "target_total",
    required=True,
    type=int,
    help="Total number of compounds desired in the subset.",
)
@click.option(
    "--min-per-source",
    "min_per_source",
    required=True,
    type=int,
    help="Minimum number of compounds guaranteed per source.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output path for the allocation manifest"
    " (CSV: folder,source,target_count,source_count).",
)
@wide_log(logger)
def generate_subset_manifest(
    source_dir: str,
    target_total: int,
    min_per_source: int,
    output_path: str,
) -> None:
    logger.info("Scanning parquet files for candidate counts", directory=source_dir)
    source_counts = _get_folder_row_counts(source_dir)

    if not source_counts:
        raise RuntimeError(f"No parquet files with rows found in {source_dir}")

    existing_manifest = _read_text(output_path)
    if existing_manifest is not None and _manifest_matches_config(
        existing_manifest, source_counts, source_dir, target_total, min_per_source
    ):
        logger.info(
            "Valid allocation already exists for current config, skipping",
            path=output_path,
        )
        return

    plan = _allocate_candidate_subset(
        source_counts=source_counts,
        target_total=target_total,
        min_per_source=min_per_source,
    )

    total_allocated = sum(a.target_count for a in plan.allocations)
    logger.info(
        "Resolved allocation",
        folder_count=len(plan.allocations),
        target_total=target_total,
        total_allocated=total_allocated,
    )

    lines = ["folder,source,target_count,source_count"]
    for allocation in plan.allocations:
        if allocation.target_count <= 0:
            logger.warning(
                "Excluding folder from manifest (target_count=0)",
                folder=allocation.folder,
            )
            continue
        source = f"{source_dir.rstrip('/')}/{allocation.folder}"
        lines.append(
            f"{allocation.folder},{source},{allocation.target_count},"
            f"{allocation.source_count}"
        )

    manifest_content = "\n".join(lines) + "\n"
    _write_text(output_path, manifest_content)

    click.echo("Done!")
