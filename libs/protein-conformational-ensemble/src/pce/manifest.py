# libs/protein-conformational-ensemble/src/pce/manifest.py

from __future__ import annotations

from typing import Any

import yaml

from protein_conformational_ensemble.errors import (
    SemanticValidationError,
    UnsupportedCapabilityError,
    UnsupportedSchemaVersionError,
)
from protein_conformational_ensemble.models import (
    KNOWN_CAPABILITIES,
    Manifest,
    TrajectoryStructure,
)
from protein_conformational_ensemble.schema import validate_schema
from protein_conformational_ensemble.weight_scheme import WEIGHT_SEMANTICS

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})

_WEIGHT_SUM_TOLERANCE = 1e-9


def parse_manifest_yaml(text: str) -> Manifest:
    raw: dict[str, Any] = yaml.safe_load(text)
    return parse_manifest_dict(raw)


def parse_manifest_dict(raw: dict[str, Any]) -> Manifest:
    validate_schema(raw)

    schema_version = raw["schema_version"]
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        msg = (
            f"Unsupported schema_version {schema_version!r}; this consumer supports "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)} (§2.5)"
        )
        raise UnsupportedSchemaVersionError(msg)

    manifest = Manifest.from_dict(raw)
    validate_semantics(manifest)
    return manifest


def validate_semantics(manifest: Manifest) -> None:
    errors: list[str] = []

    _check_conformational_state_ids_unique(manifest, errors)
    _check_topology_reference(manifest, errors)
    _check_residue_mappings(manifest, errors)
    _check_weight_scheme(manifest, errors)
    _check_capabilities(manifest, errors)

    if errors:
        details = "\n".join(f"  - {e}" for e in errors)
        msg = (
            f"Manifest failed semantic validation ({len(errors)} error(s)):\n{details}"
        )
        raise SemanticValidationError(msg)


def _check_conformational_state_ids_unique(
    manifest: Manifest, errors: list[str]
) -> None:
    seen: set[str] = set()
    for conformational_state in manifest.conformational_states:
        if conformational_state.id in seen:
            errors.append(
                f"Duplicate conformational_state id {conformational_state.id!r} (§2.4)"
            )
        seen.add(conformational_state.id)


def _check_topology_reference(manifest: Manifest, errors: list[str]) -> None:
    ref = manifest.topology_reference
    if (
        ref.conformational_state_id is not None
        and manifest.conformational_state_by_id(ref.conformational_state_id) is None
    ):
        errors.append(
            f"topology_reference.conformational_state_id {ref.conformational_state_id!r} does not reference "
            "an existing conformational_state (§3.4)"
        )


def _check_residue_mappings(manifest: Manifest, errors: list[str]) -> None:
    del manifest, errors  # documented no-op; see docstring


def _check_weight_scheme(manifest: Manifest, errors: list[str]) -> None:
    weighted_conformational_states = [
        m for m in manifest.conformational_states if m.weight is not None
    ]

    if weighted_conformational_states and manifest.weight_scheme is None:
        errors.append(
            "weight_scheme is required because at least one conformational_state declares a weight (§3.3.1)"
        )
        return

    if manifest.weight_scheme is None:
        return

    scheme_type = manifest.weight_scheme.type
    if scheme_type not in WEIGHT_SEMANTICS:
        errors.append(f"Unknown weight_scheme.type {scheme_type!r} (§3.3.2)")

    if scheme_type == "custom" and manifest.weight_scheme.custom_semantics is None:
        errors.append(
            "weight_scheme.type is 'custom' but custom_semantics is missing; "
            "required companion field (§3.3.2)"
        )

    for conformational_state in weighted_conformational_states:
        conformational_state_type = (
            conformational_state.weight.type
            if conformational_state.weight is not None
            else None
        )
        if (
            conformational_state_type is not None
            and conformational_state_type != scheme_type
        ):
            errors.append(
                f"conformational_state {conformational_state.id!r} has weight.type={conformational_state_type!r}, which "
                f"contradicts ensemble-level weight_scheme.type={scheme_type!r} (§3.3.1)"
            )

    if manifest.weight_scheme.normalized:
        total = sum(
            m.weight.value
            for m in weighted_conformational_states
            if m.weight is not None
        )
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            errors.append(
                f"weight_scheme.normalized is true but conformational_state weights sum to {total!r}, "
                f"not 1.0 +/- {_WEIGHT_SUM_TOLERANCE} (§3.3.1)"
            )


def _check_capabilities(manifest: Manifest, errors: list[str]) -> None:
    has_trajectory_conformational_state = any(
        isinstance(m.structure, TrajectoryStructure)
        for m in manifest.conformational_states
    )
    declared = set(manifest.capabilities_required)

    if has_trajectory_conformational_state and "trajectory_backed" not in declared:
        errors.append(
            "At least one conformational_state uses topology_uri/trajectory_uri but "
            "capabilities_required does not include 'trajectory_backed' (§3.1.1)"
        )


def check_capabilities_supported(
    manifest: Manifest, supported: frozenset[str] = KNOWN_CAPABILITIES
) -> None:
    unsupported = set(manifest.capabilities_required) - set(supported)
    if unsupported:
        msg = (
            f"Manifest requires capabilities not supported by this consumer: "
            f"{sorted(unsupported)} (§3.1.1)"
        )
        raise UnsupportedCapabilityError(msg)
