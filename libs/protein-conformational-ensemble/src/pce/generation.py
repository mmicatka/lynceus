# libs/protein-conformational-ensemble/src/pce/generation.py

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from pce.canonical import canonical_serialize
from pce.hashing import (
    StructureBytesResolver,
    compute_content_hash,
    default_structure_bytes,
)
from pce.manifest import SUPPORTED_SCHEMA_VERSIONS, validate_semantics
from pce.models import (
    CAPABILITY_STANDALONE_CIF,
    Manifest,
    ConformationalState,
    StandaloneStructure,
    TopologyReference,
    Weight,
    WeightScheme,
)
from pce.ensemble import MANIFEST_FILENAME

_PLACEHOLDER_HASH = "blake3:" + "0" * 64

GENERATED_SCHEMA_VERSION = max(SUPPORTED_SCHEMA_VERSIONS)


@dataclass(frozen=True, slots=True)
class ConformationalStateSpec:
    id: str
    source_path: Path
    weight_value: float | None = None
    weight_type: str | None = None
    provenance: dict | None = None


def _copy_structure_into_package(
    spec: ConformationalStateSpec, package_root: Path
) -> str:
    dest_name = f"{spec.id}{spec.source_path.suffix}"
    dest_path = package_root / dest_name
    shutil.copyfile(spec.source_path, dest_path)
    return dest_name


def _build_conformational_state(
    spec: ConformationalStateSpec, uri: str
) -> ConformationalState:
    weight = None
    if spec.weight_value is not None:
        weight = Weight(value=spec.weight_value, type=spec.weight_type)
    return ConformationalState(
        id=spec.id,
        structure=StandaloneStructure(uri=uri),
        weight=weight,
        provenance=spec.provenance,
    )


def generate_ensemble(
    *,
    ensemble_id: str,
    conformational_states_specs: list[ConformationalStateSpec],
    package_root: Path,
    weight_scheme: WeightScheme | None = None,
    topology_conformational_state_id: str | None = None,
    capabilities_required: tuple[str, ...] = (CAPABILITY_STANDALONE_CIF,),
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> Manifest:
    if not conformational_states_specs:
        msg = "generate_ensemble() requires at least one ConformationalStateSpec"
        raise ValueError(msg)

    package_root.mkdir(parents=True, exist_ok=True)

    # Copy structures first; URIs must exist on disk before hashing.
    uris = {
        spec.id: _copy_structure_into_package(spec, package_root)
        for spec in conformational_states_specs
    }
    conformational_states = tuple(
        _build_conformational_state(spec, uris[spec.id])
        for spec in conformational_states_specs
    )

    any_weighted = any(c.weight is not None for c in conformational_states)
    if any_weighted and weight_scheme is None:
        msg = (
            "At least one conformational state has a weight but no weight_scheme "
            "was provided. Per PCE_MANIFEST_CONTRACT.md, weight_scheme is required the moment "
            "any conformational state declares a weight."
        )
        raise ValueError(msg)
    if not any_weighted:
        weight_scheme = None  # never emit an unused weight_scheme

    topo_id = topology_conformational_state_id or conformational_states_specs[0].id
    topology_reference = TopologyReference(conformational_state_id=topo_id)

    provisional = Manifest(
        schema_version=GENERATED_SCHEMA_VERSION,
        id=ensemble_id,
        content_hash=_PLACEHOLDER_HASH,
        parent_ensemble=None,
        topology_reference=topology_reference,
        conformational_states=conformational_states,
        weight_scheme=weight_scheme,
        capabilities_required=capabilities_required,
    )

    real_hash = compute_content_hash(
        provisional, package_root, structure_bytes=structure_bytes
    )
    final_manifest = replace(provisional, content_hash=real_hash)

    validate_semantics(final_manifest)

    manifest_path = package_root / MANIFEST_FILENAME
    manifest_yaml = canonical_serialize(final_manifest.to_canonical())
    manifest_path.write_bytes(manifest_yaml)

    return final_manifest
