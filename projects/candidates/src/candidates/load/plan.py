# projects/candidates/src/candidates/load/plan.py


from pathlib import Path

import click
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

logger = get_lynceus_logger()


@click.command("plan_candidates")
@click.option(
    "--source-root",
    required=True,
    type=str,
    help="Directory to scan for files.",
)
@click.option(
    "--source-glob",
    default="**/*",
    show_default=True,
    type=str,
    help="Glob, relative to --source-root, selecting the files.",
)
@click.option(
    "--output-file",
    default="/tmp/manifest.json",
    show_default=True,
    type=str,
    help="File the manifest JSON is written to (read as an Argo output parameter).",
)
@wide_log(logger)
def plan_load_candidates(
    source_root: str,
    source_glob: str,
    output_file: str,
) -> None:
    click.echo(
        f"Generating file manifest for {source_root} matching '{source_glob}'..."
    )

    root_path = Path(source_root)
    if not root_path.exists() or not root_path.is_dir():
        raise click.ClickException(
            f"Source root does not exist or is not a directory: {source_root}"
        )

    paths = [p for p in root_path.glob(source_glob) if p.is_file()]

    try:
        manifest = Manifest(filepath=output_file)

        manifest.set_source_files(paths=paths, root=source_root)
        manifest.save()

    except Exception as e:
        logger.error("Failed to generate and save manifest.", error=str(e))
        raise click.ClickException(f"Failed to generate manifest: {e}")

    logger.info(
        "Generated file manifest",
        source_root=source_root,
        source_glob=source_glob,
        output_file=output_file,
        file_count=len(paths),
    )
    click.echo(f"Done! Manifest for {len(paths)} files written to {output_file}")


if __name__ == "__main__":
    plan_load_candidates()
