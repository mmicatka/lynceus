# libs/protein-conformational-ensemble/src/pce/hashing.py

from __future__ import annotations

from typing import Protocol

import fsspec
from blake3 import blake3
from fsspec.implementations.local import LocalFileSystem

from pce.canonical import canonical_serialize
from pce.models import (
    ConformationalState,
    Manifest,
    TrajectoryStructure,
)
from pce.uris import join_uri

ALGORITHM_PREFIX = "blake3"


class StructureBytesResolver(Protocol):
    def __call__(
        self,
        conformational_state: ConformationalState,
        package_root: str,
        filesystem: fsspec.AbstractFileSystem,
    ) -> bytes: ...


def _blake3_digest(data: bytes) -> bytes:
    return blake3(data).digest()


def default_structure_bytes(
    conformational_state: ConformationalState,
    package_root: str,
    filesystem: fsspec.AbstractFileSystem,
) -> bytes:
    structure = conformational_state.structure
    if isinstance(structure, TrajectoryStructure):
        msg = (
            f"Member {conformational_state.id!r} is trajectory-backed; "
            "extracting the exact frame_index byte range requires a "
            "trajectory-format-aware reader (e.g. MDAnalysis/mdtraj), "
            "which is out of scope for this reference implementation. "
            "Supply a custom StructureBytesResolver - see "
            "extract_trajectory_frame_bytes for the expected contract."
        )
        raise NotImplementedError(msg)

    uri = join_uri(package_root, structure.uri)
    with filesystem.open(uri, "rb") as f:
        return f.read()


def conformational_state_leaf_hash(
    conformational_state: ConformationalState,
    package_root: str,
    filesystem: fsspec.AbstractFileSystem,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> bytes:
    canonical_entry = canonical_serialize(conformational_state.to_canonical())
    struct_bytes = structure_bytes(conformational_state, package_root, filesystem)
    struct_digest = _blake3_digest(struct_bytes)
    return _blake3_digest(canonical_entry + struct_digest)


def merkle_root(leaf_hashes: list[bytes]) -> bytes:
    if not leaf_hashes:
        msg = "Cannot compute a Merkle root over zero leaves"
        raise ValueError(msg)

    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            _blake3_digest(level[i] + level[i + 1]) for i in range(0, len(level), 2)
        ]
    return level[0]


def compute_content_hash(
    manifest: Manifest,
    package_root: str,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
    filesystem: fsspec.AbstractFileSystem | None = None,
) -> str:
    filesystem = filesystem or LocalFileSystem()
    ordered_conformational_states = sorted(
        manifest.conformational_states, key=lambda c: c.id
    )
    leaves = [
        conformational_state_leaf_hash(
            m, package_root, filesystem, structure_bytes=structure_bytes
        )
        for m in ordered_conformational_states
    ]
    root = merkle_root(leaves)
    return f"{ALGORITHM_PREFIX}:{root.hex()}"


def verify_content_hash(
    manifest: Manifest,
    package_root: str,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
    filesystem: fsspec.AbstractFileSystem | None = None,
) -> bool:
    algorithm, _, _ = manifest.content_hash.partition(":")
    if algorithm != ALGORITHM_PREFIX:
        msg = (
            f"Unsupported content_hash algorithm {algorithm!r}; this reference "
            f"implementation only supports {ALGORITHM_PREFIX!r}"
        )
        raise NotImplementedError(msg)

    recomputed = compute_content_hash(
        manifest, package_root, structure_bytes=structure_bytes, filesystem=filesystem
    )
    return recomputed == manifest.content_hash
