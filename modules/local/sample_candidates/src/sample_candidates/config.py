# modules/local/sample_candidates/src/sample_candidates/config.py

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class FeatureKind(str, Enum):
    ARRAY = "array"
    SCALAR = "scalar"


class FeatureSpec(BaseModel, frozen=True):
    name: str
    kind: FeatureKind
    reduced_dims: int | None = Field(
        default=None,
        description="Target dimensionality after TruncatedSVD reduction. "
        "Required for array features, must be omitted for scalar features.",
    )

    @model_validator(mode="after")
    def _reduced_dims_matches_kind(self) -> "FeatureSpec":
        if self.kind is FeatureKind.ARRAY and self.reduced_dims is None:
            raise ValueError(
                f"Feature '{self.name}' is kind=array but reduced_dims "
                "was not provided."
            )
        if self.kind is FeatureKind.SCALAR and self.reduced_dims is not None:
            raise ValueError(
                f"Feature '{self.name}' is kind=scalar but reduced_dims="
                f"{self.reduced_dims} was provided; scalar features are not reduced."
            )
        if self.reduced_dims is not None and self.reduced_dims < 1:
            raise ValueError(
                f"Feature '{self.name}' reduced_dims must be >= 1, "
                f"got {self.reduced_dims}."
            )
        return self


class StratificationConfig(BaseModel):
    features: tuple[FeatureSpec, ...]

    n_projected_dims: int = Field(default=8, ge=1)
    projection_density: float = Field(
        default=1.0 / 3.0,
        gt=0.0,
        le=1.0,
        description="Fraction of nonzero entries per row in the sparse random"
        " projection matrix.",
    )
    random_seed: int = 0

    n_quantiles_per_dim: int = Field(default=10, ge=2)

    cap_per_stratum: int = Field(default=500, ge=1)
    min_stratum_size_for_cap: int = Field(
        default=1,
        ge=1,
        description="Strata with fewer rows than this are pooled into an overflow "
        "stratum rather than sampled individually.",
    )

    @field_validator("features")
    @classmethod
    def _non_empty_unique_features(
        cls, v: tuple[FeatureSpec, ...]
    ) -> tuple[FeatureSpec, ...]:
        if len(v) == 0:
            raise ValueError("features must not be empty")
        names = [f.name for f in v]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate feature names in features: {names}")
        return v

    @property
    def array_features(self) -> tuple[FeatureSpec, ...]:
        return tuple(f for f in self.features if f.kind is FeatureKind.ARRAY)

    @property
    def scalar_features(self) -> tuple[FeatureSpec, ...]:
        return tuple(f for f in self.features if f.kind is FeatureKind.SCALAR)

    @property
    def combined_feature_dim(self) -> int:
        array_dims = sum(f.reduced_dims or 0 for f in self.array_features)
        return array_dims + len(self.scalar_features)
