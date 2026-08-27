# libs/protein-conformational-ensemble/src/pce/discovery.py

from pathlib import Path
from typing import Any

import yaml

from pce.generation import (
    ConformationalStateSpec,
)
from pce.models import WeightScheme

_STRUCTURE_SUFFIXES = {".cif", ".pdb", ".mmcif"}
_WEIGHTS_FILENAME = "weights.yaml"


def _load_weights_data(members_dir: Path) -> dict[str, Any] | None:
    weights_path = members_dir / _WEIGHTS_FILENAME
    if not weights_path.exists():
        return None
    with weights_path.open() as f:
        return yaml.safe_load(f)


def discover_member_specs(
    members_dir: Path,
) -> tuple[list[ConformationalStateSpec], WeightScheme | None]:
    weights_data = _load_weights_data(members_dir)

    structure_files = sorted(
        p for p in members_dir.iterdir() if p.suffix.lower() in _STRUCTURE_SUFFIXES
    )
    if not structure_files:
        raise ValueError(
            f"No structure files ({sorted(_STRUCTURE_SUFFIXES)}) found under "
            f"{members_dir}"
        )

    weight_values: dict[str, float] = (weights_data or {}).get("values", {})
    weight_type = (weights_data or {}).get("type")

    specs = [
        ConformationalStateSpec(
            id=path.stem,
            source_path=path,
            weight_value=weight_values.get(path.stem),
            weight_type=weight_type
            if weight_values.get(path.stem) is not None
            else None,
        )
        for path in structure_files
    ]

    weight_scheme = None
    if weights_data is not None:
        weight_scheme = WeightScheme(
            type=weights_data["type"],
            normalized=weights_data.get("normalized", False),
            custom_semantics=weights_data.get("custom_semantics"),
        )

    return specs, weight_scheme
