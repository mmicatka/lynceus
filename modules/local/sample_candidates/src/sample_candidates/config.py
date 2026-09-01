# modules/local/sample_candidates/src/sample_candidates/config.py

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class StratificationConfig(BaseModel):
    fingerprint_field: str = "morgan_fp"
    fingerprint_n_bits: int = 1024

    property_fields: tuple[str, ...] = ("mw", "logp", "tpsa")

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

    @field_validator("property_fields")
    @classmethod
    def _non_empty_property_fields(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(v) == 0:
            raise ValueError("property_fields must not be empty")
        return v

    @property
    def combined_feature_dim(self) -> int:
        return self.fingerprint_n_bits + len(self.property_fields)
