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
    Member,
    StandaloneStructure,
    TopologyReference,
    Weight,
    WeightScheme,
)
from pce.package import MANIFEST_FILENAME

_PLACEHOLDER_HASH = "blake3:" + "0" * 64

GENERATED_SCHEMA_VERSION = max(SUPPORTED_SCHEMA_VERSIONS)


@dataclass(frozen=True, slots=True)
class MemberSpec:
    id: str
    source_path: Path
    weight_value: float | None = None
    weight_type: str | None = None
    provenance: dict | None = None


def _copy_structure_into_package(spec: MemberSpec, package_root: Path) -> str:
    dest_name = f"{spec.id}{spec.source_path.suffix}"
    dest_path = package_root / dest_name
    shutil.copyfile(spec.source_path, dest_path)
    return dest_name


def _build_member(spec: MemberSpec, uri: str) -> Member:
    weight = None
    if spec.weight_value is not None:
        weight = Weight(value=spec.weight_value, type=spec.weight_type)
    return Member(
        id=spec.id,
        structure=StandaloneStructure(uri=uri),
        weight=weight,
        provenance=spec.provenance,
    )


def generate_ensemble(
    *,
    ensemble_id: str,
    member_specs: list[MemberSpec],
    package_root: Path,
    weight_scheme: WeightScheme | None = None,
    topology_member_id: str | None = None,
    capabilities_required: tuple[str, ...] = (CAPABILITY_STANDALONE_CIF,),
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> Manifest:
    if not member_specs:
        msg = "generate_ensemble() requires at least one MemberSpec"
        raise ValueError(msg)

    package_root.mkdir(parents=True, exist_ok=True)

    # Copy structures first; URIs must exist on disk before hashing.
    uris = {
        spec.id: _copy_structure_into_package(spec, package_root)
        for spec in member_specs
    }
    members = tuple(_build_member(spec, uris[spec.id]) for spec in member_specs)

    any_weighted = any(m.weight is not None for m in members)
    if any_weighted and weight_scheme is None:
        msg = (
            "At least one member has a weight but no weight_scheme was provided. "
            "Per PCE_MANIFEST_CONTRACT.md, weight_scheme is required the moment "
            "any member declares a weight."
        )
        raise ValueError(msg)
    if not any_weighted:
        weight_scheme = None  # never emit an unused weight_scheme

    topo_id = topology_member_id or member_specs[0].id
    topology_reference = TopologyReference(member_id=topo_id)

    provisional = Manifest(
        schema_version=GENERATED_SCHEMA_VERSION,
        id=ensemble_id,
        content_hash=_PLACEHOLDER_HASH,
        parent_ensemble=None,
        topology_reference=topology_reference,
        members=members,
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


def generate_degenerate_ensemble(
    *,
    ensemble_id: str,
    structure_path: Path,
    package_root: Path,
    member_id: str | None = None,
    provenance: dict | None = None,
) -> Manifest:
    resolved_member_id = member_id or ensemble_id

    spec = MemberSpec(
        id=resolved_member_id,
        source_path=structure_path,
        weight_value=1.0,
        weight_type="uniform",
        provenance=provenance,
    )

    return generate_ensemble(
        ensemble_id=ensemble_id,
        member_specs=[spec],
        package_root=package_root,
        weight_scheme=WeightScheme(type="uniform", normalized=True),
        topology_member_id=resolved_member_id,
    )
