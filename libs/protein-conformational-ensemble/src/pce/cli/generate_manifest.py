# libs/protein-conformational-ensemble/src/pce/cli/generate_manifest.py

from pathlib import Path

import click

from pce.discovery import discover_member_specs
from pce.generation import generate_ensemble


@click.command(
    help="Generate a multi-member PCE manifest from a directory of member structures."
)
@click.option(
    "--members-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory containing member structures.",
)
@click.option(
    "--ensemble-id",
    type=str,
    required=True,
    help="Unique identifier for the ensemble.",
)
@click.option(
    "--outdir",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for the manifest.",
)
@click.option(
    "--topology-member-id",
    type=str,
    default=None,
    help="Defaults to the first member found if omitted.",
)
def generate_manifest(
    members_dir: Path,
    ensemble_id: str,
    outdir: Path,
    topology_member_id: str | None,
):
    member_specs, weight_scheme = discover_member_specs(members_dir)

    manifest = generate_ensemble(
        ensemble_id=ensemble_id,
        conformational_states_specs=member_specs,
        package_root=outdir,
        weight_scheme=weight_scheme,
        topology_conformational_state_id=topology_member_id,
    )

    click.echo(
        f"Wrote PCE manifest: {outdir / 'manifest.yaml'} "
        f"({len(manifest.conformational_states)} members)"
    )
