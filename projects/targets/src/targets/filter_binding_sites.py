# projects/targets/src/targets/__init__.py

import json
from pathlib import Path

import click
from pydantic import BaseModel, ConfigDict, TypeAdapter

BINDING_SITES_FILENAME = "binding_sites.json"

Coordinates = tuple[float, float, float]


class BindingSite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    site_id: str
    member_id: str
    center: Coordinates
    pocket_score: float


class SurrogateSite(BaseModel):
    ensemble: str
    site_id: str
    member_id: str
    center: Coordinates
    pocket_score: float


def load_binding_sites(path: Path) -> list[BindingSite]:
    if not path.is_file():
        raise click.ClickException(f"binding sites file not found: {path}")
    return TypeAdapter(list[BindingSite]).validate_json(path.read_bytes())


def select_sites(
    ensemble: str, sites: list[BindingSite], min_pocket_score: float
) -> list[SurrogateSite]:
    selected = [
        SurrogateSite(ensemble=ensemble, **site.model_dump())
        for site in sites
        if site.pocket_score >= min_pocket_score
    ]
    if not selected:
        raise click.ClickException(
            f"no binding sites in ensemble '{ensemble}' have "
            f"pocket_score >= {min_pocket_score}"
        )
    return selected


def resolve_sites(
    ensembles_root: Path, ensemble_ids: tuple[str, ...], min_pocket_score: float
) -> list[SurrogateSite]:
    return [
        site
        for ensemble in ensemble_ids
        for site in select_sites(
            ensemble,
            load_binding_sites(ensembles_root / ensemble / BINDING_SITES_FILENAME),
            min_pocket_score,
        )
    ]


@click.command()
@click.option(
    "--ensembles-root",
    type=click.Path(path_type=Path, file_okay=False),
    required=True,
)
@click.option("--ensemble-id", "ensemble_ids", multiple=True, required=True)
@click.option("--min-pocket-score", type=float, required=True)
def filter_binding_sites(
    ensembles_root: Path, ensemble_ids: tuple[str, ...], min_pocket_score: float
) -> None:
    sites = resolve_sites(ensembles_root, ensemble_ids, min_pocket_score)
    click.echo(json.dumps([site.model_dump(mode="json") for site in sites]))
