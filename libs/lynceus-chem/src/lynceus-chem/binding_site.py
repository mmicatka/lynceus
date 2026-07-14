# libs/lynceus-chem/src/lynceus-chem/binding_site.py

from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

Point3 = tuple[float, float, float]


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")


class PointCloud(_StrictModel):
    kind: Literal["point_cloud"] = "point_cloud"
    points: list[Point3] = Field(min_length=1)


class Sphere(_StrictModel):
    kind: Literal["sphere"] = "sphere"
    center: Point3
    radius: float = Field(gt=0)


BoundingVolume = Annotated[Union[PointCloud, Sphere], Field(discriminator="kind")]


class ResidueRef(_StrictModel):
    chain: str = Field(min_length=1)
    resid: int
    resname: str | None = None


class BindingSite(_StrictModel):
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    site_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    center: Point3
    extent: BoundingVolume
    correspondence_cluster: str | None = None
    lining_residues: list[ResidueRef] = Field(default_factory=list)
    pocket_score: float | None = None
    weight: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude_defaults=False)
