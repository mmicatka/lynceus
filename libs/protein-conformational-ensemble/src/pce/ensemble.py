# libs/protein-conformational-ensemble/src/pce/package.py


from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pce.errors import ContentHashMismatchError
from pce.hashing import (
    StructureBytesResolver,
    default_structure_bytes,
    verify_content_hash,
)
from pce.manifest import (
    check_capabilities_supported,
    parse_manifest_yaml,
)
from pce.models import Manifest

MANIFEST_FILENAME = "manifest.yaml"


@dataclass(frozen=True, slots=True)
class Ensemble:
    manifest: Manifest
    root: Path


def load_ensemble(
    root: Path,
    *,
    verify_hash: bool = True,
    structure_bytes: StructureBytesResolver = default_structure_bytes,
) -> Ensemble:
    manifest_path = root / MANIFEST_FILENAME
    manifest = parse_manifest_yaml(manifest_path.read_text(encoding="utf-8"))

    check_capabilities_supported(manifest)

    if verify_hash and not verify_content_hash(
        manifest, root, structure_bytes=structure_bytes
    ):
        msg = (
            f"content_hash mismatch for ensemble {manifest.id!r}: recomputed hash does "
            "not match manifest's declared content_hash. This indicates corruption or "
            "drift."
        )
        raise ContentHashMismatchError(msg)

    return Ensemble(manifest=manifest, root=root)
