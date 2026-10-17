# src/workflows/config/screen.py

from typing import Optional

from pydantic import Field, PositiveFloat, PositiveInt, model_validator

from workflows.config.base import StrictModel


class CandidatesConfig(StrictModel):
    sources: list[str] = Field(min_length=1)
    sub_sample: Optional[PositiveInt]


class FeaturesConfig(StrictModel):
    conformer_prefix: str
    feature_prefix: str
    feature_list: list[str] = Field(min_length=1)


class RoundConfig(StrictModel):
    active: int = Field(ge=0)
    uniform: PositiveInt

    @property
    def total(self) -> int:
        return self.active + self.uniform


class HyperparametersConfig(StrictModel):
    num_leaves: PositiveInt = 31
    n_estimators: PositiveInt = 100
    learning_rate: PositiveFloat = 0.1


class SurrogateConfig(StrictModel):
    model_prefix: str
    feature_list: list[str] = Field(min_length=1)
    validation: PositiveInt
    rounds: list[RoundConfig] = Field(min_length=1)
    hyperparameters: HyperparametersConfig = Field(
        default_factory=HyperparametersConfig
    )

    @model_validator(mode="after")
    def _first_round_is_uniform_only(self) -> "SurrogateConfig":
        if self.rounds[0].active != 0:
            raise ValueError(
                "rounds[0].active must be 0: no model exists before round 0"
            )
        return self


class FilterConfig(StrictModel):
    features: FeaturesConfig
    surrogate: SurrogateConfig

    @model_validator(mode="after")
    def _surrogate_features_are_subset(self) -> "FilterConfig":
        unknown = set(self.surrogate.feature_list) - set(self.features.feature_list)
        if unknown:
            raise ValueError(
                f"surrogate.feature_list contains features not in "
                f"features.feature_list: {sorted(unknown)}"
            )
        return self


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
