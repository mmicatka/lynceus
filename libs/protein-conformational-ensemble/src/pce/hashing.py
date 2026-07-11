# libs/protein-conformational-ensemble/src/pce/hashing.py

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from blake3 import blake3

from pce.canonical import canonical_serialize
from pce.models import Manifest, Member, TrajectoryStructure

ALGORITHM_PREFIX = "blake3"


class StructureBytesResolver(Protocol):
    def __call__(self, member: Member, package_root: Path) -> bytes: ...


def _blake3_digest(data: bytes) -> bytes:
    return blake3(data).digest()


def default_structure_bytes(member: Member, package_root: Path) -> bytes:
    structure = member.structure
    if isinstance(structure, TrajectoryStructure):
        msg = (
            f"Member {member.id!r} is trajectory-backed; extracting the exact "
            "frame_index byte range requires a trajectory-format-aware reader "
            "(e.g. MDAnalysis/mdtraj), which is out of scope for this reference "
            "implementation. Supply a custom StructureBytesResolver -- see "
            "extract_trajectory_frame_bytes for the expected contract."
        )
        raise NotImplementedError(msg)

    path = package_root / structure.uri
    return path.read_bytes()


def extract_trajectory_frame_bytes(
    member: Member,
    package_root: Path,
    *,
    frame_reader: Callable[[Path, Path, int, str], bytes] | None = None,
) -> bytes:
    structure = member.structure
    if not isinstance(structure, TrajectoryStructure):
        msg = f"Member {member.id!r} is not trajectory-backed"
        raise TypeError(msg)

    if frame_reader is None:
        msg = (
            "extract_trajectory_frame_bytes requires a frame_reader callable "
            "(path_to_trajectory, path_to_topology, frame_index, format) -> bytes; "
            "no default trajectory-format reader is bundled with this reference "
            "implementation."
        )
        raise NotImplementedError(msg)

    topology_path = package_root / structure.topology_uri
    trajectory_path = package_root / structure.trajectory_uri
    frame_bytes = frame_reader(
        trajectory_path,
        topology_path,
        structure.frame_index,
        structure.trajectory_format,
    )
    topology_bytes = topology_path.read_bytes()
    return frame_bytes + topology_bytes


def member_leaf_hash(
    member: Member,
    package_root: Path,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> bytes:
    canonical_entry = canonical_serialize(member.to_canonical())
    struct_bytes = structure_bytes(member, package_root)
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
    package_root: Path,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> str:
    ordered_members = sorted(manifest.members, key=lambda m: m.id)
    leaves = [
        member_leaf_hash(m, package_root, structure_bytes=structure_bytes)
        for m in ordered_members
    ]
    root = merkle_root(leaves)
    return f"{ALGORITHM_PREFIX}:{root.hex()}"


def verify_content_hash(
    manifest: Manifest,
    package_root: Path,
    *,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> bool:
    algorithm, _, _ = manifest.content_hash.partition(":")
    if algorithm != ALGORITHM_PREFIX:
        msg = (
            f"Unsupported content_hash algorithm {algorithm!r}; this reference "
            f"implementation only supports {ALGORITHM_PREFIX!r} (§2.3.1, §A.4)"
        )
        raise NotImplementedError(msg)

    recomputed = compute_content_hash(
        manifest, package_root, structure_bytes=structure_bytes
    )
    return recomputed == manifest.content_hash
