# src/workflows/config/screen.py

from typing import Optional

from pydantic import Field, PositiveInt

from workflows.config.base import StrictModel


class CandidatesConfig(StrictModel):
    sources: list[str] = Field(min_length=1)
    sub_sample: Optional[PositiveInt]


class FilterConfig(StrictModel):
    features: list[str] = Field(min_length=1)


class MemberConfig(StrictModel):
    pdb_id: str
    weight: float


class EnsembleConfig(StrictModel):
    id: str
    members: list[MemberConfig]

    @property
    def pdb_ids(self) -> list[str]:
        return [member.pdb_id for member in self.members]

    @property
    def weights(self) -> dict[str, float]:
        return {member.pdb_id: member.weight for member in self.members}


class TargetConfig(StrictModel):
    ensembles: list[EnsembleConfig]


class ScreenConfig(StrictModel):
    name: str
    candidates: CandidatesConfig
    filter: FilterConfig
    targets: TargetConfig
