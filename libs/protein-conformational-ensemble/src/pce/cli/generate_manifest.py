# libs/protein-conformational-ensemble/src/pce/cli/generate_manifest.py

import argparse
from pathlib import Path
from typing import Any

from pce.generation import ConformationalStateSpec, generate_ensemble
from pce.models import WeightScheme
import yaml

_STRUCTURE_SUFFIXES = {".cif", ".pdb", ".mmcif"}
_WEIGHTS_FILENAME = "weights.yaml"


def _discover_member_specs(
    members_dir: Path,
) -> tuple[list[ConformationalStateSpec], WeightScheme | None]:
    weights_path = members_dir / _WEIGHTS_FILENAME
    weights_data: dict[str, Any] | None = None
    if weights_path.exists():
        with weights_path.open() as f:
            weights_data = yaml.safe_load(f)

    structure_files = sorted(
        p for p in members_dir.iterdir() if p.suffix.lower() in _STRUCTURE_SUFFIXES
    )
    if not structure_files:
        raise ValueError(
            f"No structure files ({sorted(_STRUCTURE_SUFFIXES)}) found under {members_dir}"
        )

    weight_values: dict[str, float] = (weights_data or {}).get("values", {})
    weight_type = (weights_data or {}).get("type")

    specs = []
    for path in structure_files:
        member_id = path.stem
        weight_value = weight_values.get(member_id)
        specs.append(
            ConformationalStateSpec(
                id=member_id,
                source_path=path,
                weight_value=weight_value,
                weight_type=weight_type if weight_value is not None else None,
            )
        )

    weight_scheme = None
    if weights_data is not None:
        weight_scheme = WeightScheme(
            type=weights_data["type"],
            normalized=weights_data.get("normalized", False),
            custom_semantics=weights_data.get("custom_semantics"),
        )

    return specs, weight_scheme


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a multi-member PCE manifest from a directory of member structures."
    )
    p.add_argument("--members-dir", type=Path, required=True)
    p.add_argument("--ensemble-id", type=str, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument(
        "--topology-member-id",
        type=str,
        default=None,
        help="Defaults to the first member found (alphabetical by filename) if omitted.",
    )
    return p.parse_args()


def generate_manifest():
    args = _parse_args()
    member_specs, weight_scheme = _discover_member_specs(args.members_dir)

    manifest = generate_ensemble(
        ensemble_id=args.ensemble_id,
        conformational_states_specs=member_specs,
        package_root=args.outdir,
        weight_scheme=weight_scheme,
        topology_conformational_state_id=args.topology_member_id,
    )

    print(
        f"Wrote PCE manifest: {args.outdir / 'manifest.yaml'} ({len(manifest.conformational_states)} members)"
    )
