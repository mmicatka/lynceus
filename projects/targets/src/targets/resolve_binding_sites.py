# projects/targets/src/targets/resolve_binding_sites.py

import json
from pathlib import Path

import click

from targets.models import EnsembleBindingSites

BINDING_SITES_FILTER_PATH = Path("binding_sites") / "binding_sites_filter.json"

Coordinates = tuple[float, float, float]


def load_sites(ensembles_root: Path, ensemble_id: str) -> EnsembleBindingSites:
    path = ensembles_root / ensemble_id / BINDING_SITES_FILTER_PATH
    if not path.is_file():
        raise click.ClickException(f"filtered binding sites not found: {path}")

    ensemble_sites = EnsembleBindingSites.model_validate_json(path.read_bytes())

    if not ensemble_sites.binding_sites:
        raise click.ClickException(
            f"no binding sites in ensemble '{ensemble_id}': {path}"
        )

    if ensemble_sites.ensemble_id != ensemble_id:
        raise click.ClickException(
            f"{path} contains sites for ensemble '{ensemble_sites.ensemble_id}', "
            f"expected '{ensemble_id}'"
        )

    return ensemble_sites


@click.command()
@click.option(
    "--ensembles-root",
    type=click.Path(path_type=Path, file_okay=False),
    required=True,
)
@click.option("--ensemble-id", "ensemble_ids", multiple=True, required=True)
def resolve_binding_sites(ensembles_root: Path, ensemble_ids: tuple[str, ...]) -> None:
    ensembles = [
        load_sites(ensembles_root, ensemble_id) for ensemble_id in ensemble_ids
    ]

    click.echo(
        json.dumps([e.model_dump(mode="json", exclude_none=True) for e in ensembles])
    )
