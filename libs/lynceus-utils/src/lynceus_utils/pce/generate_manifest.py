# libs/lynceus-utils/src/lynceus_utils/pce/generate_manifest.py

from pathlib import Path

import click
from pce.discovery import discover_member_specs
from pce.generation import generate_ensemble

from lynceus_utils.storage import get_blob_storage_settings


def _resolve_package_root(
    output_path: Path, use_blob_storage: bool, bucket: str
) -> str:
    if use_blob_storage:
        return f"s3://{bucket}/{str(output_path).lstrip('/')}"
    return str(output_path)


@click.command()
@click.option("--ensemble-id", type=str, required=True)
@click.option(
    "--input-path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--output-path", type=click.Path(path_type=Path), required=True)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output manifest and structures to blob storage.",
)
@click.option("--bucket", type=str, default="lynceus", help="Output bucket name")
def generate_pce_manifest(
    ensemble_id: str,
    input_path: Path,
    output_path: Path,
    use_blob_storage: bool,
    bucket: str,
):
    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    package_root = _resolve_package_root(output_path, use_blob_storage, bucket)

    specs, weight_scheme = discover_member_specs(input_path)

    manifest = generate_ensemble(
        ensemble_id=ensemble_id,
        conformational_states_specs=specs,
        package_root=package_root,
        weight_scheme=weight_scheme,
        blob_storage_settings=blob_storage_settings,
    )
    click.echo(f"Wrote manifest for ensemble {manifest.id!r} to {package_root}")
