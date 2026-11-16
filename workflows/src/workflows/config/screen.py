# workflows/src/workflows/config/screen.py


import math
from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from workflows.config.candidates import (
    CandidatesConfig,
    FeatureTypes,
)
from workflows.config.common import (
    ConfigError,
    ConfigSlug,
    StrictModel,
    load_config,
)

WEIGHT_SUM_TOLERANCE = 1e-6

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

PdbId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[0-9][A-Za-z0-9]{3}$"),
]

Percent = Annotated[float, Field(gt=0, le=100)]


def _require_unique(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{label} must be unique, duplicated: {duplicates}")
    return values


class RoundConfig(StrictModel):
    top: int = Field(ge=0)
    random: PositiveInt

    @property
    def total(self) -> int:
        return self.top + self.random


class HyperparametersConfig(StrictModel):
    num_leaves: PositiveInt = 31
    n_estimators: PositiveInt = 100
    learning_rate: PositiveFloat = 0.1


class SurrogateConfig(StrictModel):
    feature_types: FeatureTypes
    validation: PositiveInt
    rounds: tuple[RoundConfig, ...] = Field(min_length=1)
    random_seed: int
    active_percentile: Percent
    hyperparameters: HyperparametersConfig = Field(
        default_factory=HyperparametersConfig
    )

    @model_validator(mode="after")
    def _first_round_is_random_only(self) -> Self:
        if self.rounds[0].top != 0:
            raise ValueError("rounds[0].top must be 0: no model exists before round 0")
        return self

    @property
    def total_samples(self) -> int:
        return self.validation + sum(round_.total for round_ in self.rounds)


class FilterConfig(StrictModel):
    surrogate: SurrogateConfig


class MemberConfig(StrictModel):
    pdb_id: PdbId
    weight: PositiveFloat


class EnsembleConfig(StrictModel):
    id: Label
    members: tuple[MemberConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_members(self) -> Self:
        _require_unique(self.pdb_ids, "pdb_id values")
        total = sum(member.weight for member in self.members)
        if not math.isclose(total, 1.0, abs_tol=WEIGHT_SUM_TOLERANCE):
            raise ValueError(f"member weights must sum to 1.0, got {total}")
        return self

    @property
    def pdb_ids(self) -> tuple[str, ...]:
        return tuple(member.pdb_id for member in self.members)

    @property
    def weights(self) -> dict[str, float]:
        return {member.pdb_id: member.weight for member in self.members}


class TargetConfig(StrictModel):
    ensembles: Annotated[
        tuple[EnsembleConfig, ...],
        Field(min_length=1),
        AfterValidator(
            lambda ensembles: (
                _require_unique(tuple(e.id for e in ensembles), "ensemble ids")
                and ensembles
            )
        ),
    ]
    min_pocket_score: NonNegativeFloat


class ScreenConfig(StrictModel):
    name: Label
    candidates: ConfigSlug
    targets: TargetConfig
    filter: FilterConfig

    def validate_against(self, candidates_config: CandidatesConfig) -> None:
        sample = candidates_config.samples.get(self.candidates)
        if sample is None:
            raise ConfigError(
                f"unknown candidates sample {self.candidates!r}, "
                f"available: {sorted(candidates_config.samples)}"
            )

        surrogate = self.filter.surrogate
        unknown = set(surrogate.feature_types) - set(sample.feature_types)
        if unknown:
            raise ConfigError(
                f"surrogate.feature_types not in sample {self.candidates!r} "
                f"feature_types: {sorted(feature.value for feature in unknown)}"
            )

        if surrogate.total_samples > sample.num_samples:
            raise ConfigError(
                f"surrogate requests {surrogate.total_samples} candidates "
                f"(validation + rounds) but sample {self.candidates!r} "
                f"has {sample.num_samples}"
            )


def load_screen_config(path: Path, candidates_config: CandidatesConfig) -> ScreenConfig:
    screen = load_config(path, ScreenConfig)
    screen.validate_against(candidates_config)
    return screen
