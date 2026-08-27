# libs/protein-conformational-ensemble/src/pce/weight_scheme.py

from __future__ import annotations

from dataclasses import dataclass

from protein_conformational_ensemble.models import WeightSchemeType


@dataclass(frozen=True, slots=True)
class WeightTypeSemantics:
    sums_to_one: bool
    comparable_within_ensemble: bool
    comparable_across_ensembles: bool
    valid_operations: tuple[str, ...]
    notes: str = ""


WEIGHT_SEMANTICS: dict[WeightSchemeType, WeightTypeSemantics] = {
    "equilibrium_probability": WeightTypeSemantics(
        sums_to_one=True,
        comparable_within_ensemble=True,
        comparable_across_ensembles=False,
        valid_operations=("weighted_averaging", "expectation_values"),
        notes=(
            "Comparable across ensembles only if same generation method and comparable "
            "simulation length.",
        ),
    ),
    "cluster_fraction": WeightTypeSemantics(
        sums_to_one=True,
        comparable_within_ensemble=True,
        comparable_across_ensembles=False,
        valid_operations=("ranking", "relative_importance_within_ensemble"),
        notes="Not comparable across ensembles: depends on clustering parameters.",
    ),
    "experimental_occupancy": WeightTypeSemantics(
        sums_to_one=False,
        comparable_within_ensemble=False,
        comparable_across_ensembles=False,
        valid_operations=("ranking", "presence_absence_flags"),
        notes="Sums-to-one does not hold in general (may reflect partial resolution); "
        "comparable within an ensemble only qualitatively.",
    ),
    "uniform": WeightTypeSemantics(
        sums_to_one=True,
        comparable_within_ensemble=True,
        comparable_across_ensembles=False,
        valid_operations=(),
        notes="Indicates absence of weighting information (weight = 1/N); "
        "comparable_across_ensembles is not applicable.",
    ),
    "custom": WeightTypeSemantics(
        sums_to_one=False,
        comparable_within_ensemble=False,
        comparable_across_ensembles=False,
        valid_operations=(),
        notes="Unspecified in general; MUST NOT be compared without reading the "
        "required companion `custom_semantics` field, which declares valid operations.",
    ),
}


def are_schemes_comparable(a: WeightSchemeType, b: WeightSchemeType) -> bool:
    return a == b
