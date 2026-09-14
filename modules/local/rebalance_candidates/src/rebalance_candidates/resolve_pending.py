# modules/local/rebalance_candidates/src/rebalance_candidates/resolve_pending.py

import json
import logging

import click
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _existing_keys(fs, glob_pattern: str) -> set[str]:
    try:
        return set(fs.glob(glob_pattern))
    except FileNotFoundError:
        return set()


@click.command()
@click.option(
    "--sources",
    "sources_arg",
    required=True,
    type=str,
    help="Comma-separated list of source folder paths",
)
@click.option(
    "--output-suffix",
    "output_suffix",
    required=True,
    type=str,
    help="Suffix appended to each folder name to form its"
    " expected output key, e.g. '_count.json'.",
)
@click.option(
    "--output-dir",
    "output_dir",
    required=True,
    type=str,
    help="Directory under which expected output keys are checked.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output path for the pending-folders JSON list.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Check existence and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
def resolve_pending_candidate_folders(
    sources_arg: str,
    output_suffix: str,
    output_dir: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    sources = [s for s in sources_arg.split(",") if s]
    if not sources:
        raise RuntimeError("No source folders provided")

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    output_dir_resolved = (
        f"s3://{bucket}/{output_dir.rstrip('/').lstrip('/')}"
        if use_blob_storage
        else output_dir.rstrip("/")
    )
    glob_pattern = f"{output_dir_resolved}/*{output_suffix}"

    existing = _existing_keys(fs, glob_pattern)
    existing_folders = {
        key.split("/")[-1].removesuffix(output_suffix) for key in existing
    }

    pending = []
    skipped = []
    for source in sources:
        folder = source.rstrip("/").split("/")[-1]
        if folder in existing_folders:
            skipped.append(folder)
        else:
            pending.append(source)

    logger.info(
        "Resolved pending candidate folders: %d pending, %d already complete",
        len(pending),
        len(skipped),
    )
    if skipped:
        logger.info("Skipping already-complete folders: %s", ", ".join(sorted(skipped)))

    resolved_path = (
        f"s3://{bucket}/{output_path.lstrip('/')}" if use_blob_storage else output_path
    )
    with fs.open(resolved_path, "w") as f:
        json.dump(pending, f)

    logger.info("Wrote pending folders list to %s", resolved_path)
